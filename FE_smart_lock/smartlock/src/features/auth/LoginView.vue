<script setup lang="ts">
import { ref, reactive, onScopeDispose } from 'vue'
import { isAxiosError } from 'axios'
import { useRouter } from 'vue-router'
import { auth } from '../../shared/api/index.ts'
import { errorMessage } from '../../shared/lib/presentation.js'
import AppIcon from '../../shared/ui/AppIcon.vue'
import InlineNotice from '../../shared/ui/InlineNotice.vue'
const router = useRouter()
const mode = ref('login'),
  step = ref(0),
  busy = ref(false),
  error = ref(''),
  success = ref('')
const preToken = ref(''),
  needsBind = ref(false),
  secret = ref(''),
  qr = ref(''),
  role = ref('user')
const form = reactive({ username: '', password: '', code: '', confirm: '' })
let disposed = false
function clearEnrollment() {
  preToken.value = ''
  secret.value = ''
  qr.value = ''
  form.code = ''
  form.password = ''
  form.confirm = ''
}
function back() {
  if (busy.value) return
  clearEnrollment()
  step.value = 0
  mode.value = 'login'
  error.value = ''
}
function registerMode() {
  back()
  mode.value = 'register'
  success.value = ''
}
async function prelogin() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  success.value = ''
  try {
    const response = await auth.prelogin(form.username, form.password)
    if (disposed) return
    preToken.value = response.data.pre_token
    needsBind.value = !response.data.totp_bound
    secret.value = response.data.secret || ''
    qr.value = response.data.qr_image || ''
    role.value = response.data.role || 'user'
    form.password = ''
    step.value = 1
  } catch (failure) {
    const response = isAxiosError(failure) ? failure.response : undefined
    if (!disposed)
      error.value =
        response?.data?.status === 'pending'
          ? '账户正在等待管理员审批，请稍后登录。'
          : response?.data?.status === 'rejected'
            ? '账户申请未获批准，请联系管理员。'
            : errorMessage(failure, '登录失败，请检查账户与密码')
  } finally {
    if (!disposed) busy.value = false
  }
}
async function verify() {
  if (busy.value || !/^\d{6}$/.test(form.code)) return
  busy.value = true
  error.value = ''
  try {
    const response = needsBind.value
      ? await auth.bindTotpWithPreToken(preToken.value, form.code)
      : await auth.verifyMfa(preToken.value, form.code)
    if (disposed) return
    localStorage.setItem('token', response.data.access_token)
    localStorage.setItem('username', form.username)
    localStorage.setItem('role', response.data.role || role.value)
    clearEnrollment()
    router.replace('/dashboard')
  } catch (failure) {
    const response = isAxiosError(failure) ? failure.response : undefined
    if (disposed) return
    error.value = errorMessage(failure, '验证码校验失败')
    form.code = ''
    if (response?.data?.restart_login) {
      clearEnrollment()
      step.value = 0
    }
  } finally {
    if (!disposed) busy.value = false
  }
}
async function register() {
  if (busy.value) return
  error.value = ''
  success.value = ''
  if (form.password !== form.confirm) {
    error.value = '两次密码不一致'
    return
  }
  if (form.password.length < 12 || new TextEncoder().encode(form.password).length > 72) {
    error.value = '密码至少 12 个字符，最多 72 字节'
    return
  }
  busy.value = true
  try {
    await auth.register(form.username, form.password)
    if (disposed) return
    clearEnrollment()
    mode.value = 'login'
    success.value = '注册申请已提交。管理员批准后即可登录。'
  } catch (failure) {
    if (!disposed) error.value = errorMessage(failure, '注册失败')
  } finally {
    if (!disposed) busy.value = false
  }
}
onScopeDispose(() => {
  disposed = true
  clearEnrollment()
})
</script>
<template>
  <div class="auth-page">
    <aside class="auth-aside">
      <div class="brand">
        <div class="brand-symbol"><AppIcon name="lock" :size="22" /></div>
        <div>
          <div class="brand-name">SmartLock</div>
          <div class="brand-caption">安心，从家门开始</div>
        </div>
      </div>
      <div class="auth-intro">
        <p class="eyebrow">安心，从家门开始</p>
        <h1>
          门外是世界，
          <br />
          门内是安心。
        </h1>
        <p>
          看看门前，邀请朋友，
          <br />
          让每一次回家都多一份安心。
        </p>
        <div class="auth-feature">
          <AppIcon name="shield" :size="18" />
          多因素身份验证
        </div>
        <div class="auth-feature">
          <AppIcon name="doors" :size="18" />
          按设备分配访问权限
        </div>
        <div class="auth-feature">
          <AppIcon name="records" :size="18" />
          独立追踪命令执行结果
        </div>
      </div>
      <p class="auth-footer">SMARTLOCK / 智能家居门锁与摄像头</p>
    </aside>
    <main class="auth-main">
      <div class="auth-card">
        <p class="eyebrow">
          {{
            mode === 'register'
              ? 'CREATE ACCOUNT'
              : step === 0
                ? 'WELCOME BACK'
                : 'VERIFY YOUR IDENTITY'
          }}
        </p>
        <h1>
          {{
            mode === 'register'
              ? '创建账户'
              : step === 0
                ? '欢迎回家'
                : needsBind
                  ? '绑定身份验证器'
                  : '验证你的身份'
          }}
        </h1>
        <p class="subtext">
          {{
            mode === 'register'
              ? '填写账户信息，提交后等待管理员审批。'
              : step === 0
                ? '使用账户和身份验证器，查看家门与访客。'
                : needsBind
                  ? '首次登录需绑定 TOTP 身份验证器。'
                  : '输入身份验证器当前生成的六位验证码。'
          }}
        </p>
        <div class="steps" v-if="mode === 'login'">
          <div class="step step--active">01 · 账户验证</div>
          <div class="step" :class="{ 'step--active': step === 1 }">02 · 身份验证</div>
        </div>
        <form
          v-if="step === 0"
          class="form-section"
          @submit.prevent="mode === 'register' ? register() : prelogin()"
        >
          <div class="field">
            <label for="login-username">用户名</label>
            <input
              id="login-username"
              v-model="form.username"
              autocomplete="username"
              maxlength="80"
              placeholder="输入用户名"
              required
              :disabled="busy"
            />
          </div>
          <div class="field">
            <label for="login-password">{{ mode === 'register' ? '设置密码' : '密码' }}</label>
            <input
              id="login-password"
              v-model="form.password"
              type="password"
              :autocomplete="mode === 'register' ? 'new-password' : 'current-password'"
              :minlength="mode === 'register' ? 12 : undefined"
              placeholder="输入密码"
              required
              :disabled="busy"
            />
            <p v-if="mode === 'register'" class="subtext">至少 12 个字符，最多 72 字节。</p>
          </div>
          <div v-if="mode === 'register'" class="field">
            <label for="register-confirm">确认密码</label>
            <input
              id="register-confirm"
              v-model="form.confirm"
              type="password"
              autocomplete="new-password"
              required
              :disabled="busy"
            />
          </div>
          <InlineNotice v-if="error" tone="danger">{{ error }}</InlineNotice>
          <InlineNotice v-if="success" tone="success">{{ success }}</InlineNotice>
          <button class="button button--primary button--block" :disabled="busy">
            {{ busy ? '正在提交…' : mode === 'register' ? '提交注册申请' : '继续验证' }}
            <AppIcon name="arrow" :size="17" />
          </button>
        </form>
        <form v-else class="form-section" @submit.prevent="verify">
          <div v-if="needsBind" class="auth-qr">
            <img v-if="qr" :src="qr" alt="使用身份验证器扫描此二维码" width="180" height="180" />
            <p class="subtext">扫描二维码，或手动输入下面的密钥。</p>
            <details style="width: 100%">
              <summary>查看手动登记密钥</summary>
              <p class="mono" style="margin-top: 12px">{{ secret }}</p>
            </details>
          </div>
          <div class="field">
            <label for="login-totp">身份验证器验证码</label>
            <input
              id="login-totp"
              v-model="form.code"
              inputmode="numeric"
              autocomplete="one-time-code"
              maxlength="6"
              pattern="[0-9]{6}"
              placeholder="六位数字验证码"
              required
              :disabled="busy"
            />
          </div>
          <InlineNotice v-if="error" tone="danger">{{ error }}</InlineNotice>
          <button class="button button--primary" :disabled="busy || !/^\d{6}$/.test(form.code)">
            {{ busy ? '正在验证…' : needsBind ? '完成绑定并登录' : '确认登录' }}
          </button>
        </form>
        <div class="auth-links">
          <button v-if="mode === 'register' || step !== 0" :disabled="busy" @click="back">
            返回登录
          </button>
          <button v-else :disabled="busy" @click="registerMode">创建账户</button>
          <RouterLink v-if="!busy" to="/guest">访客通行 →</RouterLink>
        </div>
      </div>
    </main>
  </div>
</template>
