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
        <button @click="logout">Logout</button>
      </div>
    </header>

    <main class="grid">
      <section class="panel video">
        <img :src="videoUrl" alt="video feed" />
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
import { lock, alarm, mfa, device, face } from '../api/index'

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
      mfaTotpCode: '',
      mfaDoorMsg: '',
      mfaDoorSuccess: false
    }
  },
  computed: {
    lockStatus() {
      return this.isLocked ? 'LOCKED' : 'UNLOCKED'
    },
    lockButtonLabel() {
      return this.isLocked ? 'Unlock' : 'Lock'
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
        alarm: 'Alarms'
      }
      this.modalTitle = titles[tab]
      this.currentModal = tab
      if (tab === 'guest') this.fetchGuestList()
      if (tab === 'face') this.loadFaceLogs()
      if (tab === 'alarm') this.fetchAlarms()
      if (tab === 'mfa') this.fetchMfaStatus()
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
      this.mfaTotpCode = ''
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
    resetMfaDoor() {
      this.showMfaDoorModal = false
      this.mfaStep = 0
      this.mfaRequestId = ''
      this.requiresTotp = false
      this.faceStatus = 'PENDING'
      this.mfaTotpCode = ''
      this.mfaDoorMsg = ''
      this.mfaDoorSuccess = false
    },
    logout() {
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      this.$router.push('/')
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
.video img { width: 100%; height: 100%; object-fit: cover; border-radius: 12px; min-height: 320px; }
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
.mono { font-family: monospace; word-break: break-all; }
</style>
