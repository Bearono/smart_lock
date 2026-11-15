const assert = require('node:assert/strict')
const { test } = require('node:test')
const credential = { unlock_token: 'test-token', device_id: 'door_a' }
const accepted = {
  data: { command_id: 'original-command', command_accepted: true, hardware_confirmed: false }
}
const flush = () => new Promise((resolve) => setImmediate(resolve))
async function modules() {
  const flow = await import('../src/features/door/doorFlow.js')
  const guest = await import('../src/features/guests/guestFlow.js')
  const status = await import('../src/features/door/commandStatus.js')
  return { ...flow, ...guest, ...status }
}
function state() {
  return {
    code: 'guest-code',
    busy: false,
    credential: null,
    commandId: '',
    stage: 'idle',
    error: '',
    disposed: false
  }
}

test('token issuance alone cannot acknowledge a command', async () => {
  const { consumeDoorToken } = await modules()
  await assert.rejects(consumeDoorToken(credential, async () => ({ data: {} })))
  await assert.rejects(consumeDoorToken({}, async () => accepted))
  assert.deepEqual(await consumeDoorToken(credential, async () => accepted), accepted.data)
})
test('guest awaits consumption and overlapping clicks do not spend another quota', async () => {
  const { createGuestFlow } = await modules()
  let finish,
    verified = 0,
    consumed = 0
  const current = state()
  const flow = createGuestFlow(current, {
    verifyGuest: async () => {
      verified++
      return { data: credential }
    },
    consumeToken: () => {
      consumed++
      return new Promise((resolve) => {
        finish = resolve
      })
    }
  })
  const pending = flow.submit()
  await flush()
  assert.equal(current.commandId, '')
  await flow.submit()
  assert.equal(verified, 1)
  assert.equal(consumed, 1)
  finish(accepted)
  await pending
  assert.equal(current.commandId, 'original-command')
  assert.equal(current.stage, 'receipt')
  assert.equal(current.code, '')
  assert.equal(current.credential, null)
})
test('guest recovers using the same credential without a second verification', async () => {
  const { createGuestFlow } = await modules()
  let verified = 0,
    attempts = 0
  const current = state()
  const flow = createGuestFlow(current, {
    verifyGuest: async () => {
      verified++
      return { data: credential }
    },
    consumeToken: async () => {
      if (++attempts === 1) throw new Error('offline')
      return accepted
    }
  })
  await flow.submit()
  assert.equal(current.stage, 'recover')
  assert.deepEqual(current.credential, credential)
  await flow.submit()
  assert.equal(verified, 1)
  assert.equal(current.commandId, 'original-command')
})
test('lost consumption response returns the original receipt', async () => {
  const { consumeDoorToken } = await modules()
  let consumed = 0
  const result = await consumeDoorToken(
    credential,
    async () => {
      consumed++
      throw new Error('response lost')
    },
    async (token, device) => {
      assert.equal(token, credential.unlock_token)
      assert.equal(device, 'door_a')
      return { data: { id: 'original-command', status: 'pending', hardware_confirmed: false } }
    }
  )
  assert.equal(consumed, 1)
  assert.equal(result.command_id, 'original-command')
  assert.equal(result.hardware_confirmed, false)
})
test('unavailable receipt recovery preserves the original error', async () => {
  const { consumeDoorToken } = await modules()
  const original = new Error('network')
  await assert.rejects(
    consumeDoorToken(
      credential,
      async () => {
        throw original
      },
      async () => {
        throw new Error('unavailable')
      }
    ),
    (failure) => failure === original
  )
})
test('lost guest verification response is marked uncertain and never retried automatically', async () => {
  const { createGuestFlow } = await modules()
  let calls = 0,
    consumed = 0
  const current = state()
  const flow = createGuestFlow(current, {
    verifyGuest: async () => {
      calls++
      throw new Error('lost response')
    },
    consumeToken: async () => {
      consumed++
    }
  })
  await flow.submit()
  await flush()
  assert.equal(current.uncertain, true)
  assert.equal(calls, 1)
  assert.equal(consumed, 0)
})
test('disposed guest ignores late credentials and does not issue a command', async () => {
  const { createGuestFlow } = await modules()
  let finish,
    consumed = 0
  const current = state()
  const flow = createGuestFlow(current, {
    verifyGuest: () =>
      new Promise((resolve) => {
        finish = resolve
      }),
    consumeToken: async () => {
      consumed++
      return accepted
    }
  })
  const pending = flow.submit()
  flow.dispose()
  finish({ data: credential })
  await pending
  assert.equal(current.credential, null)
  assert.equal(consumed, 0)
  assert.equal(current.commandId, '')
})
test('explicit authorization failure clears recoverable capability', async () => {
  const { createGuestFlow } = await modules()
  const current = state()
  current.credential = credential
  const flow = createGuestFlow(current, {
    consumeToken: async () => {
      throw { response: { status: 403 } }
    }
  })
  await flow.submit()
  assert.equal(current.credential, null)
  assert.equal(current.stage, 'idle')
})
test('execution success requires explicit hardware confirmation', async () => {
  const { normalizeCommandStatus } = await modules()
  assert.equal(normalizeCommandStatus({ status: 'executed', hardware_confirmed: true }), 'executed')
  assert.equal(normalizeCommandStatus({ status: 'executed', hardware_confirmed: false }), 'unknown')
  for (const status of ['pending', 'failed', 'expired', 'revoked', 'superseded'])
    assert.equal(normalizeCommandStatus({ status }), status)
  assert.equal(normalizeCommandStatus({ status: 'unrecognized' }), 'unknown')
})
