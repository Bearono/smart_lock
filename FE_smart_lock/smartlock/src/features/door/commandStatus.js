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
