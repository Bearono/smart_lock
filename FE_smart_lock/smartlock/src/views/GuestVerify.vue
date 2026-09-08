<template>
  <div class="page">
    <div class="card">
      <h2>Guest Access</h2>
      <p class="hint">Enter the pass code you received from the host to unlock the door.</p>

      <form v-if="!unlocked" @submit.prevent="handleVerify">
        <input
          v-model="passCode"
          placeholder="Guest pass code"
          autocomplete="off"
          spellcheck="false"
        />
        <p v-if="errorMsg" class="error">{{ errorMsg }}</p>
        <button :disabled="isLoading || !passCode">
          {{ isLoading ? 'Verifying...' : 'Verify and Unlock' }}
        </button>
        <p class="link" @click="backToLogin">Back to login</p>
      </form>

      <div v-else class="success-box">
        <p class="success">Door unlocked</p>
        <p class="hint">This token is valid for {{ expiresIn }} seconds.</p>
        <p class="mono small">{{ unlockToken }}</p>
        <button @click="reset">Verify another code</button>
        <p class="link" @click="backToLogin">Back to login</p>
      </div>
    </div>
  </div>
</template>

<script>
import { mfa } from '../api/index'

export default {
  name: 'GuestVerify',
  data() {
    return {
      passCode: '',
      isLoading: false,
      errorMsg: '',
      unlocked: false,
      unlockToken: '',
      expiresIn: 0
    }
  },
  methods: {
    async handleVerify() {
      this.errorMsg = ''
      const code = this.passCode.trim()
      if (!code) {
        this.errorMsg = 'Please enter the pass code'
        return
      }
      this.isLoading = true
      try {
        const res = await mfa.verifyGuest(code)
        this.unlockToken = res.data.unlock_token
        this.expiresIn = res.data.expires_in || 60
        this.unlocked = true
      } catch (error) {
        this.errorMsg = error?.response?.data?.msg || 'Verify failed'
      } finally {
        this.isLoading = false
      }
    },
    reset() {
      this.passCode = ''
      this.unlocked = false
      this.unlockToken = ''
      this.expiresIn = 0
      this.errorMsg = ''
    },
    backToLogin() {
      this.$router.push('/')
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
button:disabled { opacity: 0.5; cursor: not-allowed; }
.error { color: #f87171; font-size: 12px; margin-top: 8px; }
.success { color: #4ade80; font-size: 14px; margin-top: 8px; font-weight: 600; }
.hint { color: #cbd5e1; font-size: 12px; margin-top: -4px; margin-bottom: 8px; }
.link { margin-top: 12px; color: #93c5fd; cursor: pointer; text-align: center; }
.success-box { margin-top: 8px; }
.mono { word-break: break-all; font-family: monospace; margin-top: 8px; font-size: 12px; }
.small { color: #cbd5e1; }
</style>
