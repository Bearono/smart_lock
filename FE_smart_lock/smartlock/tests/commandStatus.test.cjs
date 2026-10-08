const assert = require('node:assert/strict')
const { test } = require('node:test')
const fs = require('node:fs')
const path = require('node:path')

function tracker(getCommand) {
  const root = path.join(__dirname, '../src')
  const helpers = fs
    .readFileSync(path.join(root, 'api/commandStatus.js'), 'utf8')
    .replaceAll('export ', '')
  const { commandLabels, normalizeCommandStatus } = new Function(
    helpers + '; return { commandLabels, normalizeCommandStatus }'
  )()
  const script = fs
    .readFileSync(path.join(root, 'components/CommandStatus.vue'), 'utf8')
    .match(/<script>([\s\S]*?)<\/script>/)[1]
    .replace(/^import .*$/gm, '')
    .replace('export default', 'return')
  const timers = [],
    events = []
  let now = 0
  const definition = new Function(
    'lock',
    'commandLabels',
    'normalizeCommandStatus',
    'setTimeout',
    'clearTimeout',
    'Date',
    script
  )(
    { getCommand },
    commandLabels,
    normalizeCommandStatus,
    (fn) => {
      timers.push(fn)
      return timers.length
    },
    () => {},
    { now: () => now }
  )
  const instance = {
    ...definition.data(),
    commandId: 'one',
    credential: null,
    $emit: (...event) => events.push(event)
  }
  instance.start = definition.methods.start.bind(instance)
  return {
    instance,
    timers,
    events,
    advance: (value) => {
      now = value
    },
    unmount: () => definition.beforeUnmount.call(instance)
  }
}

const flush = () => new Promise((resolve) => setImmediate(resolve))

test('tracker observes pending then confirmed execution', async () => {
  let calls = 0
  const state = tracker(async () => ({
    data: ++calls === 1 ? { status: 'pending' } : { status: 'executed', hardware_confirmed: true }
  }))
  state.instance.start()
  await flush()
  assert.equal(state.instance.status, 'pending')
  await state.timers.shift()()
  assert.equal(state.instance.status, 'executed')
  assert.deepEqual(state.events, [['settled', 'executed']])
  assert.equal(state.timers.length, 0)
})

test('unmounted tracker ignores an in-flight response', async () => {
  let finish
  const state = tracker(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  state.instance.start()
  state.unmount()
  finish({ data: { status: 'executed', hardware_confirmed: true } })
  await flush()
  assert.equal(state.events.length, 0)
  assert.equal(state.timers.length, 0)
})

test('unreachable device status ends as unknown, never success or assumed expiry', async () => {
  const state = tracker(async () => {
    throw new Error('offline')
  })
  state.instance.start()
  await flush()
  state.advance(45001)
  await state.timers.shift()()
  assert.equal(state.instance.status, 'unknown')
  assert.deepEqual(state.events, [['settled', 'unknown']])
  assert.equal(state.timers.length, 0)
})
