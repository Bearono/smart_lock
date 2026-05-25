/* eslint-disable no-unused-vars */
import axios from 'axios'
import { mockApi } from './mock'

const API_BASE = process.env.VUE_APP_API_BASE || 'http://localhost:8000'
const USE_MOCK = false

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' }
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/'
    }
    return Promise.reject(error)
  }
)

export const auth = USE_MOCK ? mockApi.auth : {
  register: (username, password, email) => api.post('/api/register', { username, password, email }),
  // 第一步：账号密码初验，返回临时通行证 + TOTP绑定状态
  prelogin: (username, email, password) => api.post('/api/login/pre', { username, email, password }),
  // 第二步A：已绑定用户验证TOTP，换正式Token
  verifyMfa: (preToken, code) => api.post('/api/login/mfa/verify', { pre_token: preToken, code }),
  // 第二步B：首次登录绑定TOTP，换正式Token
  bindTotpWithPreToken: (preToken, code) => api.post('/api/login/mfa/bind', { pre_token: preToken, code })
}

export const lock = USE_MOCK ? mockApi.lock : {
  getStatus: (deviceId = 'door_01') => api.get(`/api/lock/status?device_id=${deviceId}`),
  control: (action, deviceId = 'door_01') => api.post('/api/lock/control', { action, device_id: deviceId }),
  getHistory: (page = 1, perPage = 10) => api.get(`/api/lock/history?page=${page}&per_page=${perPage}`)
}

export const device = USE_MOCK ? mockApi.device : {
  heartbeat: (data) => api.post('/api/device/heartbeat', data),
  getStatus: (deviceId) => {
    const url = deviceId ? `/api/device/status?device_id=${deviceId}` : '/api/device/status'
    return api.get(url)
  }
}

export const mfa = USE_MOCK ? mockApi.mfa : {
  getStatus: () => api.get('/api/mfa/status'),
  bindTotp: () => api.post('/api/mfa/bind/totp'),
  verifyTotp: (code, credentialId) => api.post('/api/mfa/verify/totp', { code, credential_id: credentialId }),
  unbindTotp: () => api.post('/api/mfa/unbind/totp'),
  bindDevice: (deviceId, devicePubkey) => api.post('/api/mfa/bind/device', { device_id: deviceId, device_pubkey: devicePubkey }),
  unbindDevice: (deviceId) => api.post('/api/mfa/unbind/device', { device_id: deviceId }),
  openDoorRequest: (deviceId) => api.post('/api/mfa/open-door/request', { device_id: deviceId }),
  openDoorConfirm: (requestId, totpCode) => api.post('/api/mfa/open-door/confirm', { request_id: requestId, totp_code: totpCode }),
  sendFaceResult: (payload) => api.post('/api/mfa/open-door/face-result', payload),
  adminUnlock: (targetUsername) => api.post('/api/mfa/admin/device/unlock', { target_username: targetUsername }),
  createGuest: (guestName, validHours = 24, maxUses = 1) =>
    api.post('/api/mfa/guest/create', { guest_name: guestName, valid_hours: validHours, max_uses: maxUses }),
  verifyGuest: (passCode) => api.post('/api/mfa/guest/verify', { pass_code: passCode }),
  listGuest: () => api.get('/api/mfa/guest/list'),
  revokeGuest: (passId) => api.post(`/api/mfa/guest/revoke/${passId}`)
}

export const alarm = USE_MOCK ? mockApi.alarm : {
  trigger: (type, message) => api.post('/api/trigger_alarm', { type, message }),
  list: (status, limit = 10) => {
    const url = `/api/alarms?limit=${limit}${status ? `&status=${status}` : ''}`
    return api.get(url)
  },
  update: (alarmId, status) => api.patch(`/api/alarms/${alarmId}`, { status })
}

export const face = USE_MOCK ? mockApi.face : {
  getLogs: (page = 1, perPage = 10, passed, deviceId) => {
    let url = `/api/face/logs?page=${page}&per_page=${perPage}`
    if (passed !== undefined) url += `&passed=${passed}`
    if (deviceId) url += `&device_id=${deviceId}`
    return api.get(url)
  }
}

export default api
