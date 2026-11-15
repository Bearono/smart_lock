export const commandLabels = Object.freeze({
  pending: '命令已提交，正在等待设备执行确认',
  executed: '设备已确认本次命令执行',
  failed: '设备报告执行失败',
  expired: '命令已过期，未取得执行确认',
  revoked: '命令授权已撤销',
  superseded: '命令已被后续请求替代',
  unknown: '暂未确认执行结果。请查询原命令并核查设备状态。'
})

export function normalizeCommandStatus(data) {
  const status = data?.status
  if (!Object.hasOwn(commandLabels, status)) return 'unknown'
  if (status === 'executed' && data.hardware_confirmed !== true) return 'unknown'
  return status
}

export function commandFailureMessage(data) {
  if (data?.status !== 'failed') return ''
  const messages = {
    ACTUATOR_UNAVAILABLE:
      '本次操作已获授权，设备尚未接入锁具，无法执行实体开锁。请连接锁具驱动与状态反馈后再试。',
    FEEDBACK_MISMATCH: '设备未取得与目标一致的锁具反馈，请检查锁具和传感器。',
    ACTUATION_FAILED: '锁具动作未完成，请检查设备与驱动。系统不会自动重复开锁。',
    COMMAND_INTERRUPTED: '设备在执行期间中断，实际锁具状态未知，请现场核查。'
  }
  return messages[data.failure_reason] || ''
}
