import { consumeDoorToken } from '../api/doorFlow.js'
import { errorMessage } from './presentation.js'

export function createGuestFlow(state, api) {
  async function submit() {
    if (state.busy || state.disposed || !state.code.trim()) return
    state.uncertain = false
    state.busy = true
    state.error = ''
    let issued = !!state.credential
    try {
      if (!state.credential) {
        state.stage = 'verify'
        const response = await api.verifyGuest(state.code.trim())
        if (state.disposed) return
        state.credential = response.data
        issued = true
      }
      state.stage = 'submit'
      const result = await consumeDoorToken(state.credential, api.consumeToken, api.queryOutcome)
      if (state.disposed) return
      if (!result.command_id) throw new Error('服务端未返回命令回执，请查询原操作')
      state.receipt = state.credential
      state.credential = null
      state.code = ''
      state.commandId = result.command_id
      state.stage = 'receipt'
      state.status = 'pending'
    } catch (failure) {
      if (state.disposed) return
      const definitive = failure.response && failure.response.status < 500
      if (definitive) state.credential = null
      state.uncertain = !definitive && !issued
      state.error = errorMessage(
        failure,
        state.credential
          ? '提交结果未确认，继续时会恢复原命令，不会重新扣减验证额度。'
          : '验证结果未确认，请核查设备状态。'
      )
      state.stage = state.credential ? 'recover' : 'idle'
    } finally {
      if (!state.disposed) state.busy = false
    }
  }
  function reset() {
    state.credential = null
    state.receipt = null
    state.commandId = ''
    state.code = ''
    state.error = ''
    state.stage = 'idle'
    state.uncertain = false
  }
  function dispose() {
    state.disposed = true
    reset()
  }
  return { submit, reset, dispose }
}
