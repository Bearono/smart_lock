<script setup lang="ts">
import { ref, reactive, watch, onScopeDispose } from 'vue'
import { isAxiosError } from 'axios'
import { useRouter } from 'vue-router'
import { auth } from '../../shared/api/index.ts'
import { setAccount } from '../../shared/lib/account.ts'
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
const heading = ref<HTMLHeadingElement | null>(null)
const showPassword = ref(false)
watch([mode, step], () => heading.value?.focus(), { flush: 'post' })
let disposed = false
function clearEnrollment() {
  showPassword.value = false
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
            : response?.status === 401
              ? '用户名或密码不正确。请核对项目用户名和密码后重试。'
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
    setAccount(response.data.username || form.username, response.data.role || role.value)
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
    <main class="auth-main">
      <div class="auth-card">
        <div class="auth-identity" aria-hidden="true"><AppIcon name="lock" :size="28" /></div>
        <h1 ref="heading" tabindex="-1">
          {{
            mode === 'register'
              ? '创建账户'
              : step === 0
                ? '登录 SmartLock'
                : needsBind
                  ? '绑定身份验证器'
                  : '身份验证'
          }}
        </h1>
        <p class="auth-intro subtext">
          {{
            mode === 'register'
              ? '填写账户信息，提交后等待管理员审批。'
              : step === 0
                ? '登录后查看门前快照和管理通行权限。'
                : needsBind
                  ? '首次登录需要绑定身份验证器。'
                  : '输入身份验证器中的六位验证码。'
          }}
        </p>
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
            <div class="auth-password">
              <input
                id="login-password"
                v-model="form.password"
                :type="showPassword ? 'text' : 'password'"
                :autocomplete="mode === 'register' ? 'new-password' : 'current-password'"
                :minlength="mode === 'register' ? 12 : undefined"
                placeholder="输入密码"
                required
                :disabled="busy"
              />
              <button type="button" :disabled="busy" @click="showPassword = !showPassword">
                {{ showPassword ? '隐藏' : '显示' }}密码
              </button>
            </div>
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
        <div v-glass class="auth-links">
          <button v-if="mode === 'register' || step !== 0" :disabled="busy" @click="back">
            返回登录
          </button>
          <button v-else :disabled="busy" @click="registerMode">创建账户</button>
          <RouterLink v-if="mode === 'login' && step === 0 && !busy" to="/guest">
            使用访客凭证
            <AppIcon name="chevron" :size="16" />
          </RouterLink>
        </div>
      </div>
    </main>
  </div>
</template>
