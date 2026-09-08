<template>
  <div class="page">
    <div class="card" v-if="isRegisterMode">
      <h2>Register</h2>
      <p class="hint">New accounts require admin approval before login.</p>
      <form @submit.prevent="handleRegister">
        <input v-model="regForm.username" placeholder="Username" />
        <input v-model="regForm.email" type="email" placeholder="Email" />
        <input v-model="regForm.password" type="password" placeholder="Password" />
        <input v-model="regForm.confirmPassword" type="password" placeholder="Confirm Password" />
        <p v-if="errorMsg" class="error">{{ errorMsg }}</p>
        <p v-if="successMsg" class="success">{{ successMsg }}</p>
        <button :disabled="isLoading">{{ isLoading ? 'Submitting...' : 'Submit for approval' }}</button>
      </form>
      <p class="link" @click="backToLogin">Back to login</p>
    </div>

    <div class="card" v-else>
      <h2>SmartLock</h2>
      <p>{{ stepLabel }}</p>

      <form v-if="step === 0" @submit.prevent="handlePreLogin">
        <input v-model="form.username" placeholder="Username" />
        <input v-model="form.email" type="email" placeholder="Email" />
        <input v-model="form.password" type="password" placeholder="Password" />
        <p v-if="errorMsg" class="error">{{ errorMsg }}</p>
        <p v-if="successMsg" class="success">{{ successMsg }}</p>
        <button :disabled="isLoading">{{ isLoading ? 'Sending...' : 'Get MFA Code' }}</button>
        <p class="link" @click="goRegister">Create account</p>
        <p class="link" @click="goGuest">Guest access</p>
      </form>

      <form v-else @submit.prevent="handleMfaVerify">
        <div v-if="needsTotpBind" class="info">
          <div>First login requires TOTP binding</div>
          <div class="mono">{{ totpSecret }}</div>
          <div class="mono small">{{ totpQrUri }}</div>
        </div>

        <input v-model="form.otpCode" maxlength="6" placeholder="6-digit code" />
        <p v-if="errorMsg" class="error">{{ errorMsg }}</p>
        <button :disabled="isLoading || form.otpCode.length !== 6">
          {{ isLoading ? 'Verifying...' : (needsTotpBind ? 'Bind and Login' : 'Confirm Login') }}
        </button>
        <p class="link" @click="resetToLogin">Back</p>
      </form>
    </div>
  </div>
</template>

<script>
import { auth } from '../api/index'

export default {
  name: 'UserLogin',
  data() {
    return {
      isRegisterMode: false,
      isLoading: false,
      errorMsg: '',
      successMsg: '',
      step: 0,
      needsTotpBind: false,
      totpSecret: '',
      totpQrUri: '',
      preToken: '',
      role: 'user',
      form: {
        username: '',
        email: '',
        password: '',
        otpCode: ''
      },
      regForm: {
        username: '',
        email: '',
        password: '',
        confirmPassword: ''
      }
    }
  },
  computed: {
    stepLabel() {
      if (this.step === 0) return 'Login'
      return this.needsTotpBind ? 'TOTP Binding' : 'MFA Verification'
    }
  },
  methods: {
    resetToLogin() {
      this.step = 0
      this.errorMsg = ''
      this.form.otpCode = ''
    },
    goRegister() {
      this.isRegisterMode = true
      this.errorMsg = ''
      this.successMsg = ''
    },
    goGuest() {
      this.$router.push('/guest')
    },
    backToLogin() {
      this.isRegisterMode = false
      this.errorMsg = ''
    },
    async handlePreLogin() {
      this.errorMsg = ''
      this.successMsg = ''
      if (!this.form.username || !this.form.email || !this.form.password) {
        this.errorMsg = 'Please fill username, email and password'
        return
      }
      this.isLoading = true
      try {
        const res = await auth.prelogin(this.form.username, this.form.email, this.form.password)
        this.preToken = res.data.pre_token
        this.needsTotpBind = !res.data.totp_bound
        this.totpSecret = res.data.secret || ''
        this.totpQrUri = res.data.qr_uri || ''
        this.role = res.data.role || 'user'
        this.step = 1
      } catch (error) {
        const data = error?.response?.data
        if (data?.status === 'pending') {
          this.errorMsg = 'Your account is pending admin approval. Please wait.'
        } else if (data?.status === 'rejected') {
          this.errorMsg = 'Your registration was rejected by admin.'
        } else {
          this.errorMsg = data?.msg || 'Login failed'
        }
      } finally {
        this.isLoading = false
      }
    },
    async handleMfaVerify() {
      if (this.form.otpCode.length !== 6) {
        this.errorMsg = 'Enter a 6-digit code'
        return
      }
      this.isLoading = true
      this.errorMsg = ''
      try {
        const res = this.needsTotpBind
          ? await auth.bindTotpWithPreToken(this.preToken, this.form.otpCode)
          : await auth.verifyMfa(this.preToken, this.form.otpCode)
        localStorage.setItem('token', res.data.access_token)
        localStorage.setItem('username', this.form.username)
        localStorage.setItem('role', res.data.role || this.role || 'user')
        this.$router.push('/dashboard')
      } catch (error) {
        this.errorMsg = error?.response?.data?.msg || 'Code error'
        this.form.otpCode = ''
      } finally {
        this.isLoading = false
      }
    },
    async handleRegister() {
      this.errorMsg = ''
      this.successMsg = ''
      if (!this.regForm.username || !this.regForm.email || !this.regForm.password) {
        this.errorMsg = 'Please fill registration fields'
        return
      }
      if (this.regForm.password !== this.regForm.confirmPassword) {
        this.errorMsg = 'Passwords do not match'
        return
      }
      this.isLoading = true
      try {
        await auth.register(this.regForm.username, this.regForm.password, this.regForm.email)
        this.successMsg = 'Submitted. Please wait for admin approval before logging in.'
        this.form.username = this.regForm.username
        this.form.email = this.regForm.email
        this.regForm = { username: '', email: '', password: '', confirmPassword: '' }
        setTimeout(() => { this.isRegisterMode = false }, 1500)
      } catch (error) {
        this.errorMsg = error?.response?.data?.msg || 'Register failed'
      } finally {
        this.isLoading = false
      }
    }
  }
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f172a;
  color: #fff;
}
.card {
  width: 100%;
  max-width: 420px;
  padding: 32px;
  border-radius: 20px;
  background: rgba(17, 24, 39, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.2);
}
input, button {
  width: 100%;
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid #334155;
  background: #111827;
  color: #fff;
  box-sizing: border-box;
}
button {
  background: #4f46e5;
  border: none;
  cursor: pointer;
}
.error { color: #f87171; font-size: 12px; margin-top: 8px; }
.success { color: #4ade80; font-size: 12px; margin-top: 8px; }
.hint { color: #cbd5e1; font-size: 12px; margin-top: -4px; margin-bottom: 8px; }
.link { margin-top: 12px; color: #93c5fd; cursor: pointer; }
.info {
  margin-top: 12px;
  padding: 12px;
  background: rgba(79, 70, 229, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.35);
  border-radius: 10px;
  font-size: 12px;
}
.mono { word-break: break-all; font-family: monospace; margin-top: 8px; }
.small { color: #cbd5e1; }
</style>
