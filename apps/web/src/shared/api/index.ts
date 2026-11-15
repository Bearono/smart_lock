import axios from 'axios'
import { parseDevice, parseDevices, parseSnapshot } from './contracts.ts'
import { clearAccount } from '../lib/account.ts'

const API_BASE = import.meta.env.VITE_API_BASE || ''

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  withCredentials: true,
  xsrfCookieName: 'smartlock_csrf',
  xsrfHeaderName: 'X-CSRF-TOKEN',
  headers: { 'Content-Type': 'application/json' }
})

const PUBLIC_401_PATHS = [
  '/api/account/password',
  '/api/account/session',
  '/api/mfa/guest/verify',
  '/api/lock/unlock-token/verify',
  '/api/lock/command-status',
  '/api/mfa/open-door/',
  '/api/login/pre',
  '/api/login/mfa/verify',
  '/api/login/mfa/bind'
]

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = error.config?.url || ''
    const isPublic = PUBLIC_401_PATHS.some((p) => url.includes(p))
    if (
      error.response?.status === 401 &&
      (!isPublic || error.response?.data?.code === 'LOGIN_REQUIRED')
    ) {
      clearAccount()
      window.location.href = '/'
    }
    return Promise.reject(error)
  }
)

export const auth = {
  session: () => api.get('/api/account/session'),
  logout: () => api.post('/api/logout'),
  changePassword: (currentPassword: string, newPassword: string, code: string) =>
    api.post('/api/account/password', {
      current_password: currentPassword,
      new_password: newPassword,
      code
    }),
  register: (username: string, password: string) =>
    api.post('/api/register', { username, password }),
  prelogin: (username: string, password: string) =>
    api.post('/api/login/pre', { username, password }),
  verifyMfa: (preToken: string, code: string) =>
    api.post(
      '/api/login/mfa/verify',
      { pre_token: preToken, code },
      {
        headers: { 'X-SmartLock-Session': 'browser' }
      }
    ),
  bindTotpWithPreToken: (preToken: string, code: string) =>
    api.post(
      '/api/login/mfa/bind',
      { pre_token: preToken, code },
      {
        headers: { 'X-SmartLock-Session': 'browser' }
      }
    )
}

export const lock = {
  getCommand: (commandId: string) =>
    api.get(`/api/lock/commands/${encodeURIComponent(commandId)}`, { timeout: 5000 }),
  getTokenCommand: (unlockToken: string, deviceId: string | undefined) =>
    api.post(
      '/api/lock/command-status',
      { unlock_token: unlockToken, device_id: deviceId },
      { timeout: 5000 }
    ),
  consumeToken: (unlockToken: string, deviceId: string | undefined) =>
    api.post('/api/lock/unlock-token/verify', { unlock_token: unlockToken, device_id: deviceId }),
  control: (action: string, deviceId = 'door_01') =>
    api.post('/api/lock/control', { action, device_id: deviceId }),
  getHistory: (page = 1, perPage = 10, deviceId?: string) =>
    api.get('/api/lock/history', {
      params: { page, per_page: perPage, device_id: deviceId || undefined }
    })
}

export const device = {
  getStatus: async (deviceId?: string) => {
    const response = await api.get('/api/device/status', {
      params: deviceId ? { device_id: deviceId } : undefined
    })
    return {
      ...response,
      data: deviceId ? parseDevice(response.data) : parseDevices(response.data)
    }
  }
}

export const mfa = {
  getStatus: () => api.get('/api/mfa/status'),
  bindDevice: (deviceId: string | undefined, devicePubkey: string) =>
    api.post('/api/mfa/bind/device', { device_id: deviceId, device_pubkey: devicePubkey }),
  unbindDevice: (deviceId?: string) => api.post('/api/mfa/unbind/device', { device_id: deviceId }),
  openDoorRequest: (deviceId?: string) =>
    api.post('/api/mfa/open-door/request', { device_id: deviceId }),
  openDoorConfirm: (requestId: string, totpCode?: string) =>
    api.post('/api/mfa/open-door/confirm', { request_id: requestId, totp_code: totpCode }),
  adminUnlock: (targetUsername: string) =>
    api.post('/api/mfa/admin/device/unlock', { target_username: targetUsername }),
  createGuest: (guestName: string, validHours = 24, maxUses = 1, deviceId: string | undefined) =>
    api.post('/api/mfa/guest/create', {
      guest_name: guestName,
      valid_hours: validHours,
      max_uses: maxUses,
      device_id: deviceId
    }),
  verifyGuest: (passCode: string) => api.post('/api/mfa/guest/verify', { pass_code: passCode }),
  listGuest: () => api.get('/api/mfa/guest/list'),
  revokeGuest: (passId: number) => api.post(`/api/mfa/guest/revoke/${passId}`)
}

export const alarm = {
  list: (status: string | undefined = undefined, limit = 10) => {
    const url = `/api/alarms?limit=${limit}${status ? `&status=${status}` : ''}`
    return api.get(url)
  },
  update: (alarmId: number, status: string | undefined) =>
    api.patch(`/api/alarms/${alarmId}`, { status })
}

export const face = {
  getLogs: (
    page = 1,
    perPage = 10,
    passed: string | undefined = undefined,
    deviceId: string | undefined = undefined
  ) => {
    return api.get('/api/face/logs', {
      params: { page, per_page: perPage, passed, device_id: deviceId || undefined }
    })
  }
}

export const media = {
  clearSnapshot: (snapshotPath: string) =>
    api.post('/api/snapshot/clear', { snapshot: snapshotPath }),
  capture: async (deviceId: string) => {
    const response = await api.post('/api/video/capture', { device_id: deviceId })
    return { ...response, data: parseSnapshot(response.data) }
  },
  latest: async (deviceId?: string) => {
    const response = await api.get('/api/video/latest', { params: { device_id: deviceId } })
    return { ...response, data: parseSnapshot(response.data) }
  },
  image: (path: string) => {
    if (!/^\/api\/media\/[a-f0-9]{32}\.jpg$/.test(path))
      return Promise.reject(new Error('Invalid private image path'))
    return api.get(path, { responseType: 'blob' })
  }
}

export const admin = {
  renameDevice: (deviceId: string, displayName: string) =>
    api.put(`/api/admin/devices/${encodeURIComponent(deviceId)}/name`, {
      display_name: displayName
    }),
  evidence: () => api.get('/api/admin/security/evidence'),
  userDevices: (userId: number) => api.get(`/api/admin/users/${userId}/devices`),
  setDeviceGrant: (userId: number, deviceId: string, granted: boolean) =>
    api.put(`/api/admin/users/${userId}/devices/${encodeURIComponent(deviceId)}`, { granted }),
  listUsers: (status?: string) => {
    const url = status ? `/api/admin/users?status=${status}` : '/api/admin/users'
    return api.get(url)
  },
  approve: (userId: number) => api.post(`/api/admin/users/${userId}/approve`),
  reject: (userId: number) => api.post(`/api/admin/users/${userId}/reject`)
}

export default api
