<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { auth, mfa, admin } from '../../shared/api/index.ts'
import { useDoorSession } from '../door/useDoorSession.ts'
import { errorMessage, serverTime } from '../../shared/lib/presentation.js'
import PageHeading from '../../shared/ui/PageHeading.vue'
import InlineNotice from '../../shared/ui/InlineNotice.vue'
import EmptyState from '../../shared/ui/EmptyState.vue'
import StatusBadge from '../../shared/ui/StatusBadge.vue'
import AppDialog from '../../shared/ui/AppDialog.vue'
const router = useRouter(),
  session = useDoorSession()
const { devices, selectedId, authStatus, authError, taskActive } = session
const targetId = ref(''),
  busy = ref(false),
  error = ref(''),
  success = ref(''),
  unbindTarget = ref(''),
  passwordOpen = ref(false)
const form = reactive({ current: '', password: '', confirm: '', code: '' })
const isAdmin = localStorage.getItem('role') === 'admin'
const renameId = ref(''),
  displayName = ref('')
async function rename() {
  if (busy.value || taskActive.value) return
  busy.value = true
  error.value = ''
  success.value = ''
  try {
    await admin.renameDevice(renameId.value, displayName.value.trim())
    await session.refresh()
    success.value = '家门名称已保存'
    displayName.value = ''
  } catch (failure) {
    error.value = errorMessage(failure, '名称保存失败，请刷新后核对')
  } finally {
    busy.value = false
  }
}
const available = computed(() =>
  devices.value.filter(
    (item) => !authStatus.value?.devices?.some((binding) => binding.device_id === item.device_id)
  )
)
async function bind() {
  if (busy.value || !targetId.value || taskActive.value) return
  busy.value = true
  error.value = ''
  success.value = ''
  try {
    await mfa.bindDevice(targetId.value, '')
    success.value = '设备认证已绑定'
    targetId.value = ''
    await session.refreshAuth()
  } catch (failure) {
    error.value = errorMessage(failure, '绑定结果未确认，请刷新认证信息')
  } finally {
    busy.value = false
  }
}
async function unbind() {
  if (busy.value || taskActive.value) return
  busy.value = true
  error.value = ''
  success.value = ''
  try {
    await mfa.unbindDevice(unbindTarget.value)
    unbindTarget.value = ''
    success.value = '设备认证已解除'
    await session.refreshAuth()
  } catch (failure) {
    error.value = errorMessage(failure, '解绑结果未确认，请刷新认证信息')
  } finally {
    busy.value = false
  }
}
async function changePassword() {
  if (busy.value || taskActive.value) return
  error.value = ''
  if (form.password !== form.confirm) {
    error.value = '两次新密码不一致'
    return
  }
  if (form.password.length < 12 || new TextEncoder().encode(form.password).length > 72) {
    error.value = '密码至少 12 个字符，最多 72 字节'
    return
  }
  busy.value = true
  try {
    await auth.changePassword(form.current, form.password, form.code)
    for (const key of ['token', 'username', 'role']) localStorage.removeItem(key)
    for (const key of Object.keys(form) as Array<keyof typeof form>) form[key] = ''
    router.replace('/')
  } catch (failure) {
    error.value = errorMessage(failure, '密码修改失败')
  } finally {
    busy.value = false
  }
}
function openUnbind(id: string) {
  unbindTarget.value = id
  error.value = ''
}
function openPassword() {
  passwordOpen.value = true
  error.value = ''
}
function closePassword() {
  if (busy.value) return
  passwordOpen.value = false
  for (const key of Object.keys(form) as Array<keyof typeof form>) form[key] = ''
  error.value = ''
}
</script>
<template>
  <PageHeading
    eyebrow="安心使用"
    title="账户与安全"
    description="管理身份验证器和设备认证，维护账户访问能力。"
  >
    <button class="button" @click="session.refreshAuth">刷新认证信息</button>
  </PageHeading>
  <div class="stack">
    <InlineNotice v-if="authError" tone="danger">{{ authError }}</InlineNotice>
    <InlineNotice v-if="error && !passwordOpen && !unbindTarget" tone="danger">
      {{ error }}
    </InlineNotice>
    <InlineNotice v-if="success" tone="success">{{ success }}</InlineNotice>
    <div class="split-page">
      <section class="panel">
        <div class="panel-head">
          <div>
            <h3>设备认证绑定</h3>
            <p class="subtext">管理员授予访问权限后，还需为设备建立认证绑定。</p>
          </div>
        </div>
        <div class="panel-body stack">
          <InlineNotice v-if="taskActive" tone="warning">
            当前门控任务尚未完成，暂时不能变更认证。
          </InlineNotice>
          <form class="button-group" @submit.prevent="bind">
            <div class="field" style="flex: 1; min-width: 180px">
              <label for="bind-device">选择可绑定设备</label>
              <select id="bind-device" v-model="targetId" :disabled="busy || taskActive">
                <option value="">选择设备</option>
                <option v-for="item in available" :key="item.device_id" :value="item.device_id">
                  {{ item.display_name || item.device_id
                  }}{{ item.device_id === selectedId ? ' · 当前设备' : '' }}
                </option>
              </select>
            </div>
            <button
              class="button button--primary"
              style="align-self: end"
              :disabled="busy || taskActive || !targetId"
            >
              {{ busy ? '处理中…' : '绑定设备' }}
            </button>
          </form>
          <table v-if="authStatus?.devices?.length" class="responsive-table">
            <thead>
              <tr>
                <th>已绑定设备</th>
                <th>绑定时间 · 服务器时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="binding in authStatus.devices" :key="binding.credential_id">
                <td data-label="设备">
                  <span class="mono">{{ binding.device_id }}</span>
                </td>
                <td data-label="绑定时间">{{ serverTime(binding.created_at) }}</td>
                <td data-label="操作">
                  <button
                    class="table-action"
                    :disabled="busy || taskActive"
                    @click="openUnbind(binding.device_id)"
                  >
                    解除绑定
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <EmptyState
            v-else
            :title="authStatus ? '尚未绑定设备认证' : '认证信息尚未取得'"
            description="从上方选择已授权设备并完成绑定。"
            icon="shield"
          />
        </div>
      </section>
      <div class="stack">
        <section v-if="isAdmin" class="panel">
          <div class="panel-head"><h3>给家门起个名字</h3></div>
          <form class="panel-body form-section" @submit.prevent="rename">
            <div class="field">
              <label for="rename-device">家门</label>
              <select id="rename-device" v-model="renameId" required :disabled="busy || taskActive">
                <option value="">选择设备</option>
                <option v-for="item in devices" :key="item.device_id" :value="item.device_id">
                  {{ item.display_name || item.device_id }}
                </option>
              </select>
            </div>
            <div class="field">
              <label for="door-name">名称</label>
              <input
                id="door-name"
                v-model="displayName"
                maxlength="60"
                placeholder="例如：入户门"
                required
                :disabled="busy || taskActive"
              />
            </div>
            <button
              class="button"
              :disabled="busy || taskActive || !renameId || !displayName.trim()"
            >
              保存家门名称
            </button>
          </form>
        </section>
        <section class="panel">
          <div class="panel-head">
            <h3>身份验证器</h3>
            <StatusBadge :tone="authStatus?.totp_bound ? 'success' : 'neutral'">
              {{ authStatus ? (authStatus.totp_bound ? '已绑定' : '未绑定') : '待确认' }}
            </StatusBadge>
          </div>
          <div class="panel-body">
            <p class="subtext">
              TOTP 在登录流程中完成登记。需要验证时，请输入身份验证器生成的六位动态验证码。
            </p>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h3>账户密码</h3></div>
          <div class="panel-body stack">
            <p class="subtext">修改密码将使现有会话失效，并撤销尚未完成的开门和访客授权。</p>
            <button class="button" :disabled="taskActive" @click="openPassword">修改密码</button>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h3>人脸验证</h3></div>
          <div class="panel-body">
            <p class="subtext">
              开门时由设备摄像头完成验证。当前服务没有提供网页人脸登记接口，人员资料需通过现有设备登记流程维护。
            </p>
          </div>
        </section>
      </div>
    </div>
  </div>
  <AppDialog v-if="unbindTarget" title="解除设备认证绑定" @close="!busy && (unbindTarget = '')">
    <div class="stack">
      <p>解除 {{ unbindTarget }} 的认证绑定？相关未完成授权将被撤销。</p>
      <InlineNotice v-if="error" tone="danger">{{ error }}</InlineNotice>
      <button class="button button--danger" :disabled="busy" @click="unbind">
        {{ busy ? '处理中…' : '确认解除' }}
      </button>
    </div>
  </AppDialog>
  <AppDialog v-if="passwordOpen" title="修改密码" @close="closePassword">
    <form class="form-section" @submit.prevent="changePassword">
      <InlineNotice tone="warning">修改成功后将退出登录，相关未完成授权也会撤销。</InlineNotice>
      <div class="field">
        <label for="current-password">当前密码</label>
        <input
          id="current-password"
          v-model="form.current"
          type="password"
          autocomplete="current-password"
          required
        />
      </div>
      <div class="field">
        <label for="new-password">新密码</label>
        <input
          id="new-password"
          v-model="form.password"
          type="password"
          autocomplete="new-password"
          minlength="12"
          required
        />
        <p class="subtext">至少 12 个字符，最多 72 字节。</p>
      </div>
      <div class="field">
        <label for="confirm-password">确认新密码</label>
        <input
          id="confirm-password"
          v-model="form.confirm"
          type="password"
          autocomplete="new-password"
          required
        />
      </div>
      <div class="field">
        <label for="password-totp">身份验证器验证码</label>
        <input
          id="password-totp"
          v-model="form.code"
          inputmode="numeric"
          autocomplete="one-time-code"
          maxlength="6"
          pattern="[0-9]{6}"
          required
        />
      </div>
      <InlineNotice v-if="error" tone="danger">{{ error }}</InlineNotice>
      <button class="button button--primary" :disabled="busy">
        {{ busy ? '提交中…' : '修改密码并退出' }}
      </button>
    </form>
  </AppDialog>
</template>
