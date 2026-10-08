<script setup lang="ts">
import type { UnlockCredential } from '../door/contracts'
import { ref, reactive, toRefs, onScopeDispose } from 'vue'
import { mfa, lock } from '../../shared/api/index.ts'
import { createGuestFlow } from './guestFlow.js'
import CommandStatus from '../door/CommandStatus.vue'
import AppIcon from '../../shared/ui/AppIcon.vue'
import InlineNotice from '../../shared/ui/InlineNotice.vue'
import AppDialog from '../../shared/ui/AppDialog.vue'
const state = reactive({
  code: '',
  busy: false,
  error: '',
  credential: null as UnlockCredential | null,
  receipt: null as UnlockCredential | null,
  commandId: '',
  status: 'pending',
  stage: 'idle',
  uncertain: false,
  disposed: false
})
const { code, busy, error, credential, receipt, commandId, status, stage, uncertain } =
  toRefs(state)
const restartOpen = ref(false)
const flow = createGuestFlow(state, {
  verifyGuest: mfa.verifyGuest,
  consumeToken: lock.consumeToken,
  queryOutcome: lock.getTokenCommand
})
async function verify() {
  if (busy.value || !code.value.trim()) return
  if (uncertain.value && !credential.value) {
    restartOpen.value = true
    return
  }
  await flow.submit()
}
async function submit() {
  restartOpen.value = false
  await flow.submit()
}
function reset() {
  flow.reset()
}
onScopeDispose(flow.dispose)
</script>
<template>
  <div class="guest-page">
    <div class="brand">
      <div class="brand-symbol"><AppIcon name="lock" :size="22" /></div>
      <div>
        <div class="brand-name">SmartLock</div>
        <p class="subtext">访客通行</p>
      </div>
    </div>
    <main class="panel guest-card">
      <div class="empty-icon"><AppIcon name="guests" :size="26" /></div>
      <h1>{{ commandId ? '查看执行结果' : '欢迎来访' }}</h1>
      <p class="subtext">
        {{
          commandId
            ? '凭证已验证，开门命令已提交。请查看设备执行回执。'
            : '输入邀请人提供的访客凭证，验证后申请开门。'
        }}
      </p>
      <div class="steps">
        <div class="step step--active">01 · 验证凭证</div>
        <div class="step" :class="{ 'step--active': !!commandId }">02 · 执行确认</div>
      </div>
      <form v-if="!commandId" class="form-section" @submit.prevent="verify">
        <div class="field">
          <label for="guest-code">访客凭证</label>
          <input
            id="guest-code"
            v-model="code"
            autocomplete="off"
            spellcheck="false"
            placeholder="粘贴或输入访客凭证"
            required
            :disabled="busy || !!credential"
          />
        </div>
        <InlineNotice v-if="error" :tone="uncertain || credential ? 'warning' : 'danger'">
          {{ error }}
        </InlineNotice>
        <div
          v-if="busy"
          class="loading-line"
          role="status"
          :aria-label="stage === 'verify' ? '正在验证凭证' : '正在提交命令'"
        />
        <p v-if="credential" class="subtext mono">目标设备：{{ credential.device_id }}</p>
        <button class="button button--primary" :disabled="busy || !code.trim()">
          {{
            busy
              ? stage === 'verify'
                ? '正在验证凭证…'
                : '正在提交命令…'
              : credential
                ? '恢复原命令结果'
                : '验证并申请开门'
          }}
        </button>
        <p class="subtext">验证通过时会使用一次验证额度。请勿反复提交或刷新页面。</p>
      </form>
      <div v-else class="stack">
        <p class="subtext mono">目标设备：{{ receipt?.device_id }}</p>
        <CommandStatus
          :command-id="commandId"
          :credential="receipt || undefined"
          @settled="status = $event"
        />
        <button v-if="!['pending', 'unknown'].includes(status)" class="button" @click="reset">
          验证其他凭证
        </button>
        <p v-else class="subtext">请先确认当前操作结果。</p>
      </div>
      <div class="auth-links">
        <RouterLink to="/">返回账户登录</RouterLink>
        <span class="subtext">SMARTLOCK</span>
      </div>
    </main>
    <p class="guest-footnote">访问范围与有效期由邀请人授权</p>
    <AppDialog v-if="restartOpen" title="再次验证前请核查" @close="restartOpen = false">
      <div class="stack">
        <p>
          上一次验证响应丢失，可能已经消耗一次验证额度。请先向邀请人核查或检查设备状态，再决定是否重新验证。
        </p>
        <div class="button-group">
          <button class="button button--primary" @click="submit">已核查，重新验证</button>
          <button class="button" @click="restartOpen = false">返回</button>
        </div>
      </div>
    </AppDialog>
  </div>
</template>
