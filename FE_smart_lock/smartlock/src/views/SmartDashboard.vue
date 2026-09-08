<template>
  <div class="shell">
    <header class="topbar">
      <div>
        <h1>SmartLock Dashboard</h1>
        <p>{{ currentTime }}</p>
      </div>
      <div class="actions">
        <button @click="refreshAll">Refresh</button>
        <button @click="openTab('history')">History</button>
        <button @click="openTab('devices')">Devices</button>
        <button @click="openTab('guest')">Guest</button>
        <button @click="openTab('mfa')">MFA</button>
        <button @click="openTab('face')">Face</button>
        <button @click="openTab('alarm')">Alarms</button>
        <button v-if="isAdmin" @click="openTab('admin')">Admin</button>
        <button @click="logout">Logout</button>
      </div>
    </header>

    <main class="grid">
      <section class="panel video">
        <img :src="videoUrl" alt="video feed" />
        <div class="video-toolbar">
          <button @click="clearLiveFeed">Clear feed</button>
          <span v-if="feedMsg" class="hint">{{ feedMsg }}</span>
        </div>
      </section>

      <section class="panel">
        <h3>Lock</h3>
        <p>Device: {{ deviceId }}</p>
        <p>Status: {{ lockStatus }}</p>
        <p>Battery: {{ battery }}%</p>
        <p>Online: {{ deviceOnline ? 'YES' : 'NO' }}</p>
        <button @click="toggleLock" :disabled="loading">{{ loading ? 'Working...' : lockButtonLabel }}</button>
        <button @click="openMfaDoor">MFA Open Door</button>
      </section>
    </main>

    <section class="panel table-panel">
      <h3>Recent Logs</h3>
      <table>
        <thead><tr><th>Time</th><th>Action</th><th>User</th></tr></thead>
        <tbody>
          <tr v-for="log in recentLogs" :key="log.id">
            <td>{{ log.timestamp }}</td>
            <td>{{ log.action }}</td>
            <td>{{ log.username }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <div v-if="currentModal" class="modal">
      <div class="backdrop" @click="currentModal = null"></div>
      <div class="dialog">
        <div class="dialog-head">
          <h3>{{ modalTitle }}</h3>
          <button @click="currentModal = null">Close</button>
        </div>

        <div v-if="currentModal === 'history'">
          <table>
            <thead><tr><th>Time</th><th>Action</th><th>User</th></tr></thead>
            <tbody>
              <tr v-for="log in allLogs" :key="log.id">
                <td>{{ log.timestamp }}</td>
                <td>{{ log.action }}</td>
                <td>{{ log.username }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="currentModal === 'devices'">
          <table>
            <thead><tr><th>Device</th><th>Status</th><th>Battery</th><th>Online</th></tr></thead>
            <tbody>
              <tr v-for="d in deviceList" :key="d.device_id">
                <td>{{ d.device_id }}</td>
                <td>{{ d.status }}</td>
                <td>{{ d.battery }}</td>
                <td>{{ d.is_online ? 'YES' : 'NO' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="currentModal === 'guest'">
          <input v-model="guestForm.guest_name" placeholder="Guest name" />
          <input v-model.number="guestForm.valid_hours" type="number" placeholder="Valid hours" />
          <input v-model.number="guestForm.max_uses" type="number" placeholder="Max uses" />
          <button @click="createGuest">Create Guest</button>
          <p v-if="guestCode" class="mono">{{ guestCode }}</p>
          <table>
            <thead><tr><th>Name</th><th>Until</th><th>Uses</th></tr></thead>
            <tbody>
              <tr v-for="g in guestList" :key="g.id">
                <td>{{ g.guest_name }}</td>
                <td>{{ g.valid_until }}</td>
                <td>{{ g.used_count }}/{{ g.max_uses }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="currentModal === 'mfa'">
          <p>TOTP bound: {{ mfaStatus.totp_bound ? 'YES' : 'NO' }}</p>
          <button @click="bindTotp">Bind TOTP</button>
          <p v-if="totpSecret" class="mono">{{ totpSecret }}</p>
          <input v-model="totpVerifyCode" maxlength="6" placeholder="TOTP code" />
          <button @click="verifyTotpBind">Verify bind</button>
          <hr />
          <p>Bound devices: {{ mfaStatus.devices.length }}</p>
          <button @click="bindCurrentDevice">Bind current device</button>
          <table v-if="mfaStatus.devices.length">
            <thead><tr><th>Device</th><th>Created</th><th>Action</th></tr></thead>
            <tbody>
              <tr v-for="d in mfaStatus.devices" :key="d.credential_id">
                <td>{{ d.device_id }}</td>
                <td>{{ d.created_at }}</td>
                <td><button @click="unbindCurrentDevice(d.device_id)">Unbind</button></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="currentModal === 'face'">
          <table>
            <thead><tr><th>Time</th><th>Request</th><th>User</th><th>Score</th><th>Passed</th></tr></thead>
            <tbody>
              <tr v-for="log in faceLogs" :key="log.id">
                <td>{{ log.timestamp }}</td>
                <td>{{ log.request_id }}</td>
                <td>{{ log.face_user_id }}</td>
                <td>{{ log.similarity_score }}</td>
                <td>{{ log.passed ? 'YES' : 'NO' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="currentModal === 'alarm'">
          <table>
            <thead><tr><th>Time</th><th>Type</th><th>Message</th><th>Status</th></tr></thead>
            <tbody>
              <tr v-for="a in alarmList" :key="a.id">
                <td>{{ a.time }}</td>
                <td>{{ a.type }}</td>
                <td>{{ a.message }}</td>
                <td>{{ a.status }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="currentModal === 'admin'">
          <div class="admin-toolbar">
            <button @click="fetchPendingUsers">Pending only</button>
            <button @click="fetchAllUsers">Show all</button>
            <span v-if="adminMsg" class="hint">{{ adminMsg }}</span>
          </div>
          <table>
            <thead>
              <tr><th>ID</th><th>Username</th><th>Role</th><th>Status</th><th>Created</th><th>Action</th></tr>
            </thead>
            <tbody>
              <tr v-for="u in adminUsers" :key="u.id">
                <td>{{ u.id }}</td>
                <td>{{ u.username }}</td>
                <td>{{ u.role }}</td>
                <td>{{ u.status }}</td>
                <td>{{ u.created_at }}</td>
                <td>
                  <button v-if="u.status === 'pending'" @click="approveUser(u)">Approve</button>
                  <button v-if="u.status === 'pending'" @click="rejectUser(u)">Reject</button>
                  <button v-if="u.status !== 'pending'" @click="adminUnlockDevice(u)">Unlock device</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div v-if="showMfaDoorModal" class="modal">
      <div class="backdrop" @click="showMfaDoorModal = false"></div>
      <div class="dialog narrow">
        <div class="dialog-head">
          <h3>MFA Open Door</h3>
          <button @click="showMfaDoorModal = false">Close</button>
        </div>
        <p v-if="mfaDoorMsg">{{ mfaDoorMsg }}</p>
        <div v-if="mfaSnapshotUrl" class="snapshot-wrap">
          <img class="mfa-snapshot" :src="mfaSnapshotUrl" alt="face snapshot" />
          <button class="snapshot-clear" @click="clearSnapshot">Clear snapshot</button>
        </div>
        <div v-if="mfaStep === 1">
          <button @click="requestMfaDoor">Start Request</button>
        </div>
        <div v-else-if="mfaStep === 2">
          <p>Request: {{ mfaRequestId }}</p>
          <p>Face status: {{ faceStatus }}</p>
          <p v-if="requiresTotp">TOTP required</p>
          <input v-if="requiresTotp" v-model="mfaTotpCode" maxlength="6" placeholder="TOTP code" />
          <button @click="confirmMfaDoor" :disabled="requiresTotp && mfaTotpCode.length !== 6">Confirm Door</button>
        </div>
        <div v-else-if="mfaStep === 3">
          <p>{{ mfaDoorSuccess ? 'Door unlocked' : 'Failed' }}</p>
          <button @click="resetMfaDoor">Reset</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { lock, alarm, mfa, device, face, admin } from '../api/index'

export default {
  name: 'SmartDashboard',
  data() {
    return {
      currentTime: '',
      deviceId: 'door_01',
      isLocked: true,
      battery: 0,
      deviceOnline: false,
      loading: false,
      videoUrl: 'http://localhost:8000/video_feed',
      currentModal: null,
      modalTitle: '',
      allLogs: [],
      recentLogs: [],
      deviceList: [],
      guestList: [],
      guestForm: { guest_name: '', valid_hours: 24, max_uses: 1 },
      guestCode: '',
      mfaStatus: { totp_bound: false, devices: [] },
      totpSecret: '',
      totpVerifyCode: '',
      totpCredentialId: null,
      faceLogs: [],
      alarmList: [],
      showMfaDoorModal: false,
      mfaStep: 0,
      mfaRequestId: '',
      requiresTotp: false,
      faceStatus: 'PENDING',
      mfaSnapshotUrl: '',
      mfaTotpCode: '',
      mfaDoorMsg: '',
      mfaDoorSuccess: false,
      role: localStorage.getItem('role') || 'user',
      adminUsers: [],
      adminMsg: '',
      feedMsg: ''
    }
  },
  computed: {
    lockStatus() {
      return this.isLocked ? 'LOCKED' : 'UNLOCKED'
    },
    lockButtonLabel() {
      return this.isLocked ? 'Unlock' : 'Lock'
    },
    isAdmin() {
      return this.role === 'admin'
    }
  },
  async mounted() {
    this.tick()
    setInterval(this.tick, 1000)
    await this.refreshAll()
  },
  methods: {
    tick() {
      this.currentTime = new Date().toLocaleString()
    },
    async refreshAll() {
      await Promise.all([
        this.fetchLockStatus(),
        this.fetchHistory(),
        this.fetchDevices(),
        this.fetchAlarms(),
        this.fetchMfaStatus()
      ])
    },
    openTab(tab) {
      const titles = {
        history: 'History',
        devices: 'Devices',
        guest: 'Guest',
        mfa: 'MFA',
        face: 'Face',
        alarm: 'Alarms',
        admin: 'Admin'
      }
      this.modalTitle = titles[tab]
      this.currentModal = tab
      if (tab === 'guest') this.fetchGuestList()
      if (tab === 'face') this.loadFaceLogs()
      if (tab === 'alarm') this.fetchAlarms()
      if (tab === 'mfa') this.fetchMfaStatus()
      if (tab === 'admin') this.fetchPendingUsers()
    },
    async fetchLockStatus() {
      try {
        const res = await lock.getStatus(this.deviceId)
        this.isLocked = res.data.status === 'LOCKED'
        this.battery = res.data.battery || 0
        this.deviceOnline = true
      } catch {
        this.deviceOnline = false
      }
    },
    async toggleLock() {
      this.loading = true
      try {
        await lock.control(this.isLocked ? 'UNLOCK' : 'LOCK', this.deviceId)
        await Promise.all([
          this.fetchLockStatus(),
          this.fetchDevices(),
          this.fetchHistory()
        ])
      } finally {
        this.loading = false
      }
    },
    async fetchHistory() {
      const res = await lock.getHistory(1, 20)
      this.allLogs = res.data.data || []
      this.recentLogs = this.allLogs.slice(0, 5)
    },
    async fetchDevices() {
      const res = await device.getStatus()
      this.deviceList = Array.isArray(res.data) ? res.data : [res.data]
    },
    async fetchAlarms() {
      const res = await alarm.list(null, 20)
      this.alarmList = res.data || []
    },
    async fetchGuestList() {
      const res = await mfa.listGuest()
      this.guestList = res.data || []
    },
    async createGuest() {
      const res = await mfa.createGuest(this.guestForm.guest_name, this.guestForm.valid_hours, this.guestForm.max_uses)
      this.guestCode = res.data.pass_code
      await this.fetchGuestList()
    },
    async fetchMfaStatus() {
      const res = await mfa.getStatus()
      this.mfaStatus = res.data
    },
    async bindTotp() {
      const res = await mfa.bindTotp()
      this.totpSecret = res.data.secret
      this.totpCredentialId = res.data.credential_id || null
      this.totpVerifyCode = ''
    },
    async verifyTotpBind() {
      try {
        await mfa.verifyTotp(this.totpVerifyCode, this.totpCredentialId)
        await this.fetchMfaStatus()
      } catch (error) {
        this.mfaDoorMsg = error?.response?.data?.msg || 'Verify failed'
      }
    },
    async bindCurrentDevice() {
      try {
        await mfa.bindDevice(this.deviceId, '')
        this.mfaDoorMsg = `Device ${this.deviceId} bound`
        await this.fetchMfaStatus()
      } catch (error) {
        this.mfaDoorMsg = error?.response?.data?.msg || 'Bind device failed'
      }
    },
    async unbindCurrentDevice(deviceId) {
      try {
        await mfa.unbindDevice(deviceId)
        this.mfaDoorMsg = `Device ${deviceId} unbound`
        await this.fetchMfaStatus()
      } catch (error) {
        this.mfaDoorMsg = error?.response?.data?.msg || 'Unbind device failed'
      }
    },
    async loadFaceLogs() {
      const res = await face.getLogs(1, 15)
      this.faceLogs = res.data.data || []
    },
    openMfaDoor() {
      const bound = (this.mfaStatus.devices || []).some(d => d.device_id === this.deviceId)
      if (!bound) {
        this.currentModal = 'mfa'
        this.modalTitle = 'MFA'
        this.mfaDoorMsg = `Bind device ${this.deviceId} first`
        return
      }
      this.showMfaDoorModal = true
      this.mfaStep = 1
      this.mfaDoorMsg = ''
      this.mfaDoorSuccess = false
      this.faceStatus = 'PENDING'
      this.mfaSnapshotUrl = ''
      this.mfaTotpCode = ''
    },
    absoluteBackendUrl(path) {
      if (!path) return ''
      if (/^https?:\/\//.test(path)) return path
      const base = process.env.VUE_APP_API_BASE || 'http://localhost:8000'
      return `${base.replace(/\/$/, '')}${path.startsWith('/') ? path : `/${path}`}`
    },
    async requestMfaDoor() {
      this.mfaStep = 1
      this.mfaDoorMsg = ''
      try {
        const res = await mfa.openDoorRequest(this.deviceId)
        this.mfaRequestId = res.data.request_id
        this.requiresTotp = !!res.data.requires_totp
        const backendReply = res.data.device_dispatch?.backend_reply || {}
        this.faceStatus = backendReply.msg || 'DISPATCHED'
        const snapshot = res.data.device_dispatch?.snapshot || backendReply.snapshot_url || backendReply.snapshot
        this.mfaSnapshotUrl = this.absoluteBackendUrl(snapshot)
        if (this.mfaSnapshotUrl) {
          this.videoUrl = `${this.videoUrl.split('?')[0]}?t=${Date.now()}`
        }
        this.mfaDoorMsg = res.data.device_dispatch
          ? `Device linked: ${res.data.device_dispatch.device_url}`
          : 'Face challenge sent to device'
        this.mfaStep = 2
      } catch (error) {
        this.faceStatus = 'FAILED'
        this.mfaDoorMsg = error?.response?.data?.msg || 'Open door request failed'
        this.mfaStep = 0
      }
    },
    async confirmMfaDoor() {
      try {
        this.mfaStep = 3
        const res = await mfa.openDoorConfirm(this.mfaRequestId, this.requiresTotp ? this.mfaTotpCode : undefined)
        this.mfaDoorSuccess = !!res.data.unlock_token
        this.mfaDoorMsg = res.data.msg || 'OK'
        await Promise.all([
          this.fetchHistory(),
          this.fetchLockStatus(),
          this.fetchDevices()
        ])
      } catch (error) {
        this.mfaDoorSuccess = false
        this.mfaDoorMsg = error?.response?.data?.msg || 'Confirm failed'
      }
    },
    async clearSnapshot() {
      const url = this.mfaSnapshotUrl
      this.mfaSnapshotUrl = ''
      if (!url) return
      const idx = url.indexOf('/static/captures/')
      if (idx < 0) return
      const path = url.slice(idx)
      try {
        await mfa.clearSnapshot(path)
      } catch (error) {
        this.mfaDoorMsg = error?.response?.data?.msg || 'Clear failed'
      }
    },
    async clearLiveFeed() {
      this.feedMsg = ''
      try {
        await mfa.clearSnapshot('')
        this.videoUrl = `${this.videoUrl.split('?')[0]}?t=${Date.now()}`
        this.feedMsg = 'Live feed cleared'
      } catch (error) {
        this.feedMsg = error?.response?.data?.msg || 'Clear failed'
      }
    },
    resetMfaDoor() {
      this.showMfaDoorModal = false
      this.mfaStep = 0
      this.mfaRequestId = ''
      this.requiresTotp = false
      this.faceStatus = 'PENDING'
      this.mfaSnapshotUrl = ''
      this.mfaTotpCode = ''
      this.mfaDoorMsg = ''
      this.mfaDoorSuccess = false
    },
    logout() {
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      localStorage.removeItem('role')
      this.$router.push('/')
    },
    async fetchPendingUsers() {
      this.adminMsg = ''
      try {
        const res = await admin.listPending()
        this.adminUsers = res.data || []
        if (!this.adminUsers.length) this.adminMsg = 'No pending users'
      } catch (error) {
        this.adminMsg = error?.response?.data?.msg || 'Load failed'
      }
    },
    async fetchAllUsers() {
      this.adminMsg = ''
      try {
        const res = await admin.listUsers()
        this.adminUsers = res.data || []
      } catch (error) {
        this.adminMsg = error?.response?.data?.msg || 'Load failed'
      }
    },
    async approveUser(user) {
      try {
        await admin.approve(user.id)
        this.adminMsg = `Approved ${user.username}`
        await this.fetchPendingUsers()
      } catch (error) {
        this.adminMsg = error?.response?.data?.msg || 'Approve failed'
      }
    },
    async rejectUser(user) {
      try {
        await admin.reject(user.id)
        this.adminMsg = `Rejected ${user.username}`
        await this.fetchPendingUsers()
      } catch (error) {
        this.adminMsg = error?.response?.data?.msg || 'Reject failed'
      }
    },
    async adminUnlockDevice(user) {
      this.adminMsg = ''
      try {
        const res = await mfa.adminUnlock(user.username)
        this.adminMsg = res?.data?.msg || `Unlocked ${user.username}`
      } catch (error) {
        this.adminMsg = error?.response?.data?.msg || 'Unlock failed'
      }
    }
  }
}
</script>

<style scoped>
.shell {
  min-height: 100vh;
  background: #0b1220;
  color: #fff;
  padding: 20px;
  box-sizing: border-box;
}
.topbar, .actions, .grid { display: flex; gap: 12px; }
.topbar { justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.actions { flex-wrap: wrap; }
.grid { display: grid; grid-template-columns: 2fr 1fr; }
.panel {
  background: rgba(17, 24, 39, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 16px;
  padding: 16px;
}
.video { display: flex; flex-direction: column; gap: 8px; }
.video img { width: 100%; height: 100%; object-fit: cover; border-radius: 12px; min-height: 320px; }
.video-toolbar { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.snapshot-wrap { position: relative; }
.snapshot-clear { position: absolute; top: 12px; right: 8px; background: #b91c1c; border-color: #7f1d1d; }
.table-panel { margin-top: 12px; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th, td { padding: 8px; border-bottom: 1px solid #243044; text-align: left; font-size: 12px; }
button, input {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #334155;
  background: #111827;
  color: #fff;
}
button { cursor: pointer; }
.modal { position: fixed; inset: 0; z-index: 100; }
.backdrop { position: absolute; inset: 0; background: rgba(0,0,0,0.7); }
.dialog {
  position: relative;
  z-index: 1;
  width: min(960px, 92vw);
  margin: 60px auto;
  background: #111827;
  border: 1px solid #334155;
  border-radius: 16px;
  padding: 16px;
}
.dialog.narrow { width: min(560px, 92vw); }
.dialog-head { display: flex; justify-content: space-between; align-items: center; }
.mfa-snapshot { width: 100%; max-height: 260px; object-fit: cover; border-radius: 10px; margin: 8px 0; border: 1px solid #334155; }
.admin-toolbar { display: flex; gap: 8px; align-items: center; margin-top: 8px; flex-wrap: wrap; }
.hint { color: #cbd5e1; font-size: 12px; }
.mono { font-family: monospace; word-break: break-all; }
</style>
