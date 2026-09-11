const assert = require('node:assert/strict')
const { test } = require('node:test')
const fs = require('node:fs')
const path = require('node:path')

const src = path.join(__dirname, '../src')
const flowSource = fs.readFileSync(path.join(src, 'api/doorFlow.js'), 'utf8').replace('export async function', 'async function')
const consumeDoorToken = new Function(flowSource + '; return consumeDoorToken')()
const credential = { unlock_token: 'test-token', device_id: 'door_a' }
const accepted = { data: { command_accepted: true, hardware_confirmed: false } }

function component(name, mfa, lock) {
  const text = fs.readFileSync(path.join(src, 'views', name + '.vue'), 'utf8')
  const script = text.match(/<script>([\s\S]*?)<\/script>/)[1]
    .replace(/^import .*$/gm, '').replace('export default', 'return')
  const definition = new Function('mfa', 'lock', 'consumeDoorToken', 'localStorage', script)(
    mfa, lock, consumeDoorToken, { getItem: () => null })
  const instance = definition.data()
  for (const [name, method] of Object.entries(definition.methods)) instance[name] = method.bind(instance)
  return instance
}

test('token issuance alone cannot acknowledge a command', async () => {
  await assert.rejects(consumeDoorToken(credential, async () => ({ data: {} })))
  await assert.rejects(consumeDoorToken({}, async () => accepted))
  assert.deepEqual(await consumeDoorToken(credential, async (token, device) => {
    assert.equal(token, credential.unlock_token)
    assert.equal(device, credential.device_id)
    return accepted
  }), accepted.data)
})

test('guest waits for consumption and ignores duplicate clicks', async () => {
  let finish, verifyCount = 0, consumeCount = 0
  const guest = component('GuestVerify', { verifyGuest: async () => { verifyCount++; return { data: credential } } }, {
    consumeToken: () => { consumeCount++; return new Promise(resolve => { finish = resolve }) }
  })
  guest.passCode = 'guest-code'
  const pending = guest.handleVerify()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(guest.unlocked, false)
  await guest.handleVerify()
  assert.equal(verifyCount, 1)
  assert.equal(consumeCount, 1)
  finish(accepted)
  await pending
  assert.equal(guest.unlocked, true)
})

test('guest retries consumption without spending a second guest use', async () => {
  let issued = 0, attempts = 0
  const guest = component('GuestVerify', { verifyGuest: async () => { issued++; return { data: credential } } }, {
    consumeToken: async () => { if (++attempts === 1) throw new Error('network'); return accepted }
  })
  guest.passCode = 'guest-code'
  await guest.handleVerify()
  assert.equal(guest.unlocked, false)
  assert.deepEqual(guest.credential, credential)
  await guest.handleVerify()
  assert.equal(guest.unlocked, true)
  assert.equal(issued, 1)
})

test('dashboard consumes once and status refresh cannot reverse accepted outcome', async () => {
  let issued = 0, attempts = 0
  const dashboard = component('SmartDashboard', {
    openDoorConfirm: async () => { issued++; return { data: credential } }
  }, { consumeToken: async () => { if (++attempts === 1) throw new Error('offline'); return accepted } })
  dashboard.fetchHistory = async () => { throw new Error('refresh failed') }
  dashboard.fetchLockStatus = async () => {}
  dashboard.fetchDevices = async () => {}
  await dashboard.confirmMfaDoor()
  assert.equal(dashboard.mfaDoorSuccess, false)
  assert.deepEqual(dashboard.pendingCredential, credential)
  await dashboard.confirmMfaDoor()
  assert.equal(dashboard.mfaDoorSuccess, true)
  assert.equal(issued, 1)
  assert.match(dashboard.mfaDoorMsg, /Status refresh failed/)
})

test('dashboard unlock button starts MFA rather than calling direct control', async () => {
  const dashboard = component('SmartDashboard', {}, { control: () => { throw new Error('must not call') } })
  let started = false
  dashboard.openMfaDoor = () => { started = true }
  dashboard.isLocked = true
  await dashboard.toggleLock()
  assert.equal(started, true)
})
