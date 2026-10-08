const actions = {
  REMOTE_LOCK: '上锁命令已提交',
  TOKEN_UNLOCK: '开门命令已提交',
  UNLOCK_TOKEN_ISSUED: '开门授权已签发',
  GUEST_TOKEN_ISSUED: '访客验证通过',
  ADMIN_APPROVE: '管理员批准账户',
  ADMIN_REJECT: '管理员拒绝账户'
}
export function actionLabel(value) {
  return actions[value] || value || '未提供'
}
export function serverTime(value) {
  return value
    ? String(value)
        .replace('T', ' ')
        .replace(/\.\d+$/, '')
    : '尚未上报'
}
export function lockState(value) {
  return { LOCKED: '已锁', UNLOCKED: '已解锁', UNKNOWN: '未知' }[value] || '未知'
}
export function cameraState(value) {
  return { ONLINE: '在线', OFFLINE: '离线', ERROR: '异常', UNKNOWN: '未知' }[value] || '未知'
}
export function errorMessage(error, fallback = '暂时无法完成，请稍后重试') {
  const status = error?.response?.status
  const message = error?.response?.data?.msg
  const known = {
    'Invalid TOTP code': '验证码不正确，请重新开始验证',
    'Authentication failed': '本次验证失败，请重新开始',
    'Face verification missing': '尚未取得通过的人脸验证结果',
    'Authentication session expired': '验证会话已过期，请重新开始',
    'Device not bound': '请先在账户与安全中绑定该设备',
    'Device authorization revoked or locked': '设备认证权限已撤销或受限',
    'Invalid pass code': '访客凭证无效',
    'Invalid credentials': '账户或密码不正确'
  }
  if (known[message]) return known[message]
  if (status === 403) return '没有执行此操作的权限，或授权已失效'
  if (status === 423) return '认证已锁定，请联系管理员解除限制'
  if (status === 429) return '请求过于频繁，请稍后再试'
  return message || fallback
}
export function guestState(pass) {
  // Naive server timestamps cannot safely be compared with a browser timezone.
  if (!pass.is_active) return { label: '已撤销', tone: 'neutral' }
  if (pass.used_count >= pass.max_uses) return { label: '额度用尽', tone: 'warning' }
  return { label: '已启用', tone: 'success' }
}
