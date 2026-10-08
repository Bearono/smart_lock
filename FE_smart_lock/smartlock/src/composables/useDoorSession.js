import { computed, ref, onScopeDispose, inject } from 'vue'
import { device, mfa, lock } from '../api'
import { consumeDoorToken } from '../api/doorFlow'
import { errorMessage } from '../domain/presentation'

export const doorSessionKey = Symbol('door-session')
export function useDoorSession() {
  const session = inject(doorSessionKey)
  if (!session) throw new Error('Door session requires the application layout')
  return session
}

// Owned by the authenticated layout: route changes must not abandon receipts.
export function createDoorSession() {
  const devices = ref([]),
    selectedId = ref(''),
    refreshing = ref(false),
    error = ref('')
  const authStatus = ref(null),
    authError = ref('')
  const hasDeviceData = ref(false)
  const flowAction = ref('开门')
  const busy = ref(false),
    phase = ref('idle'),
    flowError = ref(''),
    flowDeviceId = ref('')
  const requestId = ref(''),
    requiresTotp = ref(false),
    totp = ref(''),
    credential = ref(null)
  const command = ref(null),
    commandStatus = ref(''),
    snapshotPath = ref('')
  const selected = computed(() => devices.value.find((item) => item.device_id === selectedId.value))
  const bound = computed(() =>
    authStatus.value?.devices?.some((item) => item.device_id === selectedId.value && item.is_active)
  )
  const taskActive = computed(
    () =>
      busy.value ||
      ['face', 'confirm', 'recover'].includes(phase.value) ||
      (command.value && ['pending', 'unknown'].includes(commandStatus.value))
  )
  let disposed = false,
    generation = 0,
    authGeneration = 0,
    timer

  async function refreshAuth() {
    const current = ++authGeneration
    authError.value = ''
    try {
      const response = await mfa.getStatus()
      if (!disposed && current === authGeneration) authStatus.value = response.data
    } catch (failure) {
      if (!disposed && current === authGeneration) {
        authStatus.value = null
        authError.value = errorMessage(failure, '认证准备情况加载失败')
      }
    }
  }
  async function refresh() {
    if (refreshing.value || disposed) return
    const current = ++generation
    refreshing.value = true
    error.value = ''
    try {
      const response = await device.getStatus()
      if (disposed || current !== generation) return
      devices.value = Array.isArray(response.data) ? response.data : [response.data]
      hasDeviceData.value = true
      if (!devices.value.some((item) => item.device_id === selectedId.value)) {
        selectedId.value = devices.value[0]?.device_id || ''
      }
    } catch (failure) {
      if (!disposed && current === generation)
        error.value = errorMessage(failure, '设备状态获取失败，以下为上次取得的信息')
    } finally {
      if (!disposed && current === generation) refreshing.value = false
    }
  }
  function select(id) {
    if (taskActive.value || !devices.value.some((item) => item.device_id === id)) return false
    selectedId.value = id
    resetFlow()
    return true
  }
  function resetFlow() {
    if (busy.value) return
    phase.value = 'idle'
    flowError.value = ''
    requestId.value = ''
    credential.value = null
    totp.value = ''
    requiresTotp.value = false
    snapshotPath.value = ''
  }
  function accept(result, action) {
    if (!result.command_id || result.command_accepted !== true)
      throw new Error('服务端未确认接收命令，请核查设备状态')
    command.value = { id: result.command_id, deviceId: flowDeviceId.value, action }
    commandStatus.value = 'pending'
    credential.value = null
    totp.value = ''
    phase.value = 'submitted'
    refresh()
  }
  async function startFace() {
    if (taskActive.value || !selectedId.value || !bound.value) return
    resetFlow()
    flowAction.value = '开门'
    flowDeviceId.value = selectedId.value
    phase.value = 'face'
    busy.value = true
    try {
      const response = await mfa.openDoorRequest(flowDeviceId.value)
      if (disposed) return
      requestId.value = response.data.request_id
      requiresTotp.value = !!response.data.requires_totp
      const dispatch = response.data.device_dispatch
      const reply = dispatch?.backend_reply || {}
      snapshotPath.value = dispatch?.snapshot || reply.snapshot_url || reply.snapshot || ''
      phase.value = 'confirm'
      if (dispatch?.status === 'pending')
        flowError.value = '尚未取得人脸结果。确认前请等待设备完成验证。'
    } catch (failure) {
      if (!disposed) {
        phase.value = 'failed'
        flowError.value = errorMessage(failure, '人脸验证请求未确认，请核查后重新开始')
      }
    } finally {
      if (!disposed) busy.value = false
    }
  }
  async function confirm() {
    if (busy.value || !['confirm', 'recover'].includes(phase.value)) return
    if (!credential.value && requiresTotp.value && !/^\d{6}$/.test(totp.value)) {
      flowError.value = '请输入六位数字验证码'
      return
    }
    busy.value = true
    flowError.value = ''
    try {
      if (!credential.value) {
        const response = await mfa.openDoorConfirm(
          requestId.value,
          requiresTotp.value ? totp.value : undefined
        )
        if (disposed) return
        credential.value = response.data
      }
      const result = await consumeDoorToken(
        credential.value,
        lock.consumeToken,
        lock.getTokenCommand
      )
      if (!disposed) accept(result, '开门')
    } catch (failure) {
      if (disposed) return
      const definitive = failure?.response && failure.response.status < 500
      if (definitive) credential.value = null
      phase.value = credential.value ? 'recover' : 'failed'
      flowError.value = errorMessage(
        failure,
        credential.value
          ? '提交结果暂未确认。恢复时会查询原命令，请勿重新验证。'
          : '验证结果未确认，请核查设备状态后重新开始'
      )
      totp.value = ''
    } finally {
      if (!disposed) busy.value = false
    }
  }
  async function requestLock() {
    if (taskActive.value || !selectedId.value || !bound.value) return
    resetFlow()
    flowAction.value = '上锁'
    busy.value = true
    flowDeviceId.value = selectedId.value
    try {
      const response = await lock.control('LOCK', flowDeviceId.value)
      if (!disposed) accept(response.data, '上锁')
    } catch (failure) {
      if (!disposed) {
        phase.value = 'failed'
        flowError.value = errorMessage(
          failure,
          '上锁请求结果不确定，请先检查设备状态，系统不会自动重发'
        )
      }
    } finally {
      if (!disposed) busy.value = false
    }
  }
  function settled(status) {
    commandStatus.value = status
    refresh()
  }
  async function initialize() {
    await Promise.allSettled([refresh(), refreshAuth()])
    if (!disposed)
      timer = setInterval(() => {
        if (!document.hidden) refresh()
      }, 15000)
  }
  onScopeDispose(() => {
    disposed = true
    generation++
    authGeneration++
    clearInterval(timer)
    credential.value = null
    totp.value = ''
    snapshotPath.value = ''
  })
  return {
    devices,
    hasDeviceData,
    selectedId,
    selected,
    refreshing,
    error,
    authStatus,
    authError,
    bound,
    busy,
    phase,
    flowError,
    flowDeviceId,
    flowAction,
    requestId,
    requiresTotp,
    totp,
    command,
    commandStatus,
    taskActive,
    snapshotPath,
    refresh,
    refreshAuth,
    initialize,
    select,
    startFace,
    confirm,
    requestLock,
    resetFlow,
    settled
  }
}
