/* eslint-disable no-unused-vars */
// 模拟数据配置
const mockDelay = 600

const mockData = {
  // ========== 认证 ==========
  login: { access_token: 'mock_jwt_token_' + Date.now() },
  register: { msg: 'Registered successfully' },

  // ========== 门锁状态 ==========
  lockStatus: {
    device_id: 'door_01',
    status: 'LOCKED',
    battery: 87,
    last_update: new Date().toISOString().slice(0, 19).replace('T', ' ')
  },

  // ========== 历史记录 ==========
  lockHistory: {
    total: 28,
    pages: 3,
    current_page: 1,
    data: [
      { id: 28, username: 'admin', action: '远程开锁', timestamp: '2026-05-23 14:32:10' },
      { id: 27, username: 'admin', action: '远程锁定', timestamp: '2026-05-23 14:30:00' },
      { id: 26, username: 'Mom', action: '指纹开锁', timestamp: '2026-05-23 12:15:33' },
      { id: 25, username: 'Guest_张三', action: '访客开锁', timestamp: '2026-05-23 11:00:05' },
      { id: 24, username: 'admin', action: '远程开锁', timestamp: '2026-05-22 22:10:00' },
      { id: 23, username: 'admin', action: 'MFA远程开门', timestamp: '2026-05-22 21:55:00' },
      { id: 22, username: 'System', action: '报警触发: 检测到异常震动', timestamp: '2026-05-22 20:00:00' },
      { id: 21, username: 'Delivery', action: '访客开锁', timestamp: '2026-05-22 15:30:00' },
      { id: 20, username: 'admin', action: '远程锁定', timestamp: '2026-05-22 08:00:00' },
      { id: 19, username: 'Dad', action: '指纹开锁', timestamp: '2026-05-21 19:45:00' }
    ]
  },

  // ========== 设备列表 ==========
  deviceStatus: [
    {
      device_id: 'door_01',
      status: 'LOCKED',
      battery: 87,
      is_online: true,
      last_update: new Date().toISOString().slice(0, 19).replace('T', ' ')
    },
    {
      device_id: 'door_02',
      status: 'UNLOCKED',
      battery: 65,
      is_online: true,
      last_update: new Date().toISOString().slice(0, 19).replace('T', ' ')
    },
    {
      device_id: 'door_03',
      status: 'LOCKED',
      battery: 23,
      is_online: false,
      last_update: '2026-05-22 10:00:00'
    }
  ],

  // ========== 报警记录 ==========
  alarms: [
    {
      id: 1,
      alarm_type: '入侵报警',
      message: '检测到前门异常震动',
      snapshot_path: null,
      status: 'pending',
      timestamp: new Date().toISOString().slice(0, 19).replace('T', ' ')
    },
    {
      id: 2,
      alarm_type: '门未关警告',
      message: '后门长时间处于开启状态',
      snapshot_path: null,
      status: 'pending',
      timestamp: new Date(Date.now() - 300000).toISOString().slice(0, 19).replace('T', ' ')
    },
    {
      id: 3,
      alarm_type: '密码破解报警',
      message: '检测到连续5次密码错误',
      snapshot_path: null,
      status: 'resolved',
      timestamp: new Date(Date.now() - 86400000).toISOString().slice(0, 19).replace('T', ' ')
    }
  ],

  // ========== MFA状态 ==========
  mfaStatus: {
    totp_bound: true,
    devices: [
      { credential_id: 1, device_id: 'iPhone-Admin', is_active: true, created_at: '2026-05-01 10:00:00' },
      { credential_id: 2, device_id: 'iPad-Family', is_active: true, created_at: '2026-05-10 14:30:00' }
    ]
  },

  // ========== 访客列表 ==========
  guestList: [
    {
      id: 1,
      guest_name: '快递员小王',
      pass_code: '******',
      valid_until: new Date(Date.now() + 86400000).toISOString(),
      max_uses: 3,
      used_count: 1,
      is_active: true
    },
    {
      id: 2,
      guest_name: '保洁阿姨',
      pass_code: '******',
      valid_until: new Date(Date.now() - 3600000).toISOString(),
      max_uses: 1,
      used_count: 1,
      is_active: false
    }
  ],

  // ========== 人脸日志 ==========
  faceLogs: {
    total: 15,
    pages: 2,
    current_page: 1,
    data: [
      { id: 15, request_id: 'req_xxx', device_id: 'door_01', expected_username: 'admin', face_user_id: 'admin', similarity_score: 0.92, passed: true, timestamp: new Date().toISOString().slice(0, 19).replace('T', ' ') },
      { id: 14, request_id: 'req_yyy', device_id: 'door_01', expected_username: 'Mom', face_user_id: 'Mom', similarity_score: 0.88, passed: true, timestamp: new Date(Date.now() - 3600000).toISOString().slice(0, 19).replace('T', ' ') },
      { id: 13, request_id: 'req_zzz', device_id: 'door_01', expected_username: 'admin', face_user_id: 'Unknown', similarity_score: 0.31, passed: false, timestamp: new Date(Date.now() - 7200000).toISOString().slice(0, 19).replace('T', ' ') },
      { id: 12, request_id: 'req_aaa', device_id: 'door_02', expected_username: 'Dad', face_user_id: 'Dad', similarity_score: 0.95, passed: true, timestamp: new Date(Date.now() - 10800000).toISOString().slice(0, 19).replace('T', ' ') }
    ]
  }
}

// 生成随机ID
const genId = () => Math.floor(Math.random() * 90000 + 10000)

// 模拟延迟
const delay = (ms = mockDelay) => new Promise(resolve => setTimeout(resolve, ms))

// 模拟API响应
export const mockApi = {
  // ========== 认证 ==========
  auth: {
    register: async (_username, _password) => {
      await delay()
      return { data: { msg: 'Registered successfully' }, status: 201 }
    },
    // 第一步：账号密码初验，返回临时通行证 + TOTP绑定状态
    prelogin: async (username, email, password) => {
      await delay()
      if (!username || !password) {
        throw { response: { status: 401, data: { msg: 'Invalid credentials' } } }
      }
      // 模拟：用户名包含 "new" 则未绑定TOTP，否则已绑定
      const totpBound = !username.toLowerCase().includes('new')
      const preToken = 'pre_' + Math.random().toString(36).substring(2)
      if (totpBound) {
        return {
          data: {
            pre_token: preToken,
            totp_bound: true,
            msg: 'MFA required'
          }
        }
      } else {
        return {
          data: {
            pre_token: preToken,
            totp_bound: false,
            secret: 'JBSWY3DPEHPK3PXP',
            qr_uri: `otpauth://totp/SmartLock:${username}?secret=JBSWY3DPEHPK3PXP&issuer=SmartLock`,
            credential_id: genId(),
            msg: 'TOTP binding required'
          }
        }
      }
    },
    // 第二步A：已绑定用户验证TOTP，换正式Token
    verifyMfa: async (preToken, code) => {
      await delay()
      if (code && code.length === 6) {
        return { data: { access_token: 'mock_jwt_token_' + Date.now(), username: 'user' } }
      }
      throw { response: { status: 401, data: { msg: 'Invalid TOTP code' } } }
    },
    // 第二步B：首次登录绑定TOTP，换正式Token
    bindTotpWithPreToken: async (preToken, code) => {
      await delay()
      // code为空表示跳过绑定
      return { data: { access_token: 'mock_jwt_token_' + Date.now(), username: 'user' } }
    }
  },

  // ========== 门锁控制 ==========
  lock: {
    getStatus: async (deviceId) => {
      await delay()
      return { data: { ...mockData.lockStatus, device_id: deviceId || 'door_01' } }
    },
    control: async (action, _deviceId) => {
      await delay()
      const newStatus = action === 'UNLOCK' ? 'UNLOCKED' : 'LOCKED'
      return {
        data: {
          status: 'success',
          msg: `指令已下发并更新状态为 ${action}`,
          new_status: newStatus
        }
      }
    },
    getHistory: async (_page = 1, _perPage = 10) => {
      await delay()
      return { data: mockData.lockHistory }
    }
  },

  // ========== 设备 ==========
  device: {
    heartbeat: async (data) => {
      await delay(200)
      return { data: { msg: 'Heartbeat received', device: data } }
    },
    getStatus: async (deviceId) => {
      await delay()
      if (deviceId) {
        return { data: mockData.deviceStatus.find(d => d.device_id === deviceId) || mockData.deviceStatus[0] }
      }
      return { data: mockData.deviceStatus }
    }
  },

  // ========== MFA ==========
  mfa: {
    getStatus: async () => {
      await delay()
      return { data: mockData.mfaStatus }
    },
    bindTotp: async () => {
      await delay()
      return {
        data: {
          msg: 'TOTP secret generated',
          secret: 'JBSWY3DPEHPK3PXP',
          qr_uri: 'otpauth://totp/SmartLock:admin?secret=JBSWY3DPEHPK3PXP&issuer=SmartLock',
          credential_id: genId()
        }
      }
    },
    verifyTotp: async (code, _credentialId) => {
      await delay()
      if (code && code.length === 6) {
        return { data: { msg: 'TOTP verified' } }
      }
      throw { response: { status: 401, data: { msg: 'Invalid TOTP code' } } }
    },
    unbindTotp: async () => {
      await delay()
      return { data: { msg: 'TOTP unbound successfully' } }
    },
    bindDevice: async (_deviceId) => {
      await delay()
      return { data: { msg: 'Device bound successfully' } }
    },
    unbindDevice: async (_deviceId) => {
      await delay()
      return { data: { msg: 'Device unbound successfully' } }
    },
    openDoorRequest: async (_deviceId) => {
      await delay()
      return {
        data: {
          msg: 'Auth session created',
          request_id: 'mock_request_' + genId(),
          nonce: 'mock_nonce_' + genId(),
          requires_face: true,
          requires_totp: new Date().getHours() >= 22 || new Date().getHours() < 6
        }
      }
    },
    openDoorConfirm: async (_requestId, _totpCode) => {
      await delay()
      return {
        data: {
          msg: 'Authentication successful',
          unlock_token: 'mock_unlock_token_' + genId(),
          expires_in: 60
        }
      }
    },
    adminUnlock: async (targetUsername) => {
      await delay()
      return { data: { msg: `Device for ${targetUsername} has been successfully unlocked.` } }
    },
    createGuest: async (guestName, validHours, maxUses) => {
      await delay()
      return {
        data: {
          msg: 'Guest pass created',
          pass_code: 'GC' + Math.random().toString(36).substring(2, 10).toUpperCase(),
          valid_until: new Date(Date.now() + validHours * 3600000).toISOString(),
          max_uses: maxUses
        }
      }
    },
    verifyGuest: async (_passCode) => {
      await delay()
      return {
        data: {
          msg: 'Guest pass verified',
          unlock_token: 'mock_guest_token_' + genId(),
          expires_in: 60
        }
      }
    },
    listGuest: async () => {
      await delay()
      return { data: mockData.guestList }
    },
    revokeGuest: async (_passId) => {
      await delay()
      return { data: { msg: 'Guest pass revoked' } }
    }
  },

  // ========== 报警 ==========
  alarm: {
    trigger: async (_type, _message) => {
      await delay()
      return { data: { status: 'success', snapshot: null } }
    },
    list: async (status, limit = 10) => {
      await delay()
      let list = mockData.alarms
      if (status) list = list.filter(a => a.status === status)
      return { data: list.slice(0, limit) }
    },
    update: async (alarmId, status) => {
      await delay()
      return { data: { id: alarmId, status } }
    }
  },

  // ========== 人脸日志 ==========
  face: {
    getLogs: async (_page = 1, _perPage = 10) => {
      await delay()
      return { data: mockData.faceLogs }
    }
  }
}

export default mockApi