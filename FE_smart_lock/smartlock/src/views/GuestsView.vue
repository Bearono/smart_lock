<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { mfa } from '../api'
import { useResource } from '../composables/useResource'
import { useDoorSession } from '../composables/useDoorSession'
import { errorMessage, serverTime, guestState } from '../domain/presentation'
import PageHeading from '../components/ui/PageHeading.vue'
import InlineNotice from '../components/ui/InlineNotice.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import StatusBadge from '../components/ui/StatusBadge.vue'
import AppDialog from '../components/ui/AppDialog.vue'
import AppIcon from '../components/ui/AppIcon.vue'
const { devices, selectedId, authStatus } = useDoorSession()
const resource = useResource(mfa.listGuest, [])
const { data, loading, error } = resource
const form = reactive({ name: '', deviceId: '', hours: 24, uses: 1 })
const createOpen = ref(false),
  busy = ref(false),
  mutationError = ref(''),
  result = ref(null),
  revokeTarget = ref(null),
  copied = ref(false)
const eligibleDevices = computed(() =>
  devices.value.filter((item) =>
    authStatus.value?.devices?.some(
      (binding) => binding.device_id === item.device_id && binding.is_active
    )
  )
)
function openCreate() {
  form.deviceId = eligibleDevices.value.some((item) => item.device_id === selectedId.value)
    ? selectedId.value
    : eligibleDevices.value[0]?.device_id || ''
  mutationError.value = ''
  result.value = null
  createOpen.value = true
}
async function create() {
  if (busy.value) return
  mutationError.value = ''
  if (
    !form.deviceId ||
    !Number.isInteger(form.hours) ||
    form.hours < 1 ||
    form.hours > 168 ||
    !Number.isInteger(form.uses) ||
    form.uses < 1 ||
    form.uses > 100
  ) {
    mutationError.value = '请选择设备，并填写有效的整数时长与验证额度'
    return
  }
  busy.value = true
  try {
    result.value = (await mfa.createGuest(form.name, form.hours, form.uses, form.deviceId)).data
    form.name = ''
    copied.value = false
    await resource.load()
  } catch (failure) {
    mutationError.value = errorMessage(failure, '创建结果未确认，请先刷新凭证列表，避免重复创建')
  } finally {
    busy.value = false
  }
}
async function copy() {
  try {
    await navigator.clipboard.writeText(result.value.pass_code)
    copied.value = true
  } catch {
    mutationError.value = '无法访问剪贴板，请手动选择并复制凭证'
  }
}
async function revoke() {
  if (busy.value) return
  busy.value = true
  mutationError.value = ''
  try {
    await mfa.revokeGuest(revokeTarget.value.id)
    revokeTarget.value = null
    await resource.load()
  } catch (failure) {
    mutationError.value = errorMessage(failure, '撤销结果未确认，请刷新列表核查')
  } finally {
    busy.value = false
  }
}
onMounted(resource.load)
function askRevoke(pass) {
  revokeTarget.value = pass
  mutationError.value = ''
}
</script>
<template>
  <PageHeading
    eyebrow="VISITOR ACCESS"
    title="访客"
    description="管理自己创建的访客凭证，按设备限定有效时间与验证额度。"
  >
    <button class="button" :disabled="loading" @click="resource.load">刷新</button>
    <button class="button button--primary" @click="openCreate">
      <AppIcon name="guests" :size="18" />
      创建访客凭证
    </button>
  </PageHeading>
  <div class="stack">
    <InlineNotice v-if="error" tone="danger">{{ error }}</InlineNotice>
    <section class="panel">
      <div class="panel-head">
        <div>
          <h3>我的访客凭证</h3>
          <p class="subtext">
            额度在验证并签发开门授权时扣减，不代表成功开门次数。时间由服务器提供。
          </p>
        </div>
      </div>
      <div v-if="loading" class="loading-line" />
      <div class="table-scroll">
        <table v-if="data.length" class="responsive-table">
          <thead>
            <tr>
              <th>访客</th>
              <th>设备</th>
              <th>有效期至</th>
              <th>验证额度</th>
              <th>启用状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="pass in data" :key="pass.id">
              <td data-label="访客">{{ pass.guest_name || '未命名访客' }}</td>
              <td data-label="设备">
                <span class="mono">{{ pass.device_id }}</span>
              </td>
              <td data-label="有效期至">{{ serverTime(pass.valid_until) }}</td>
              <td data-label="额度">
                已验证 {{ pass.used_count }} / {{ pass.max_uses }} · 剩余
                {{ Math.max(0, pass.max_uses - pass.used_count) }}
              </td>
              <td data-label="状态">
                <StatusBadge :tone="guestState(pass).tone">
                  {{ guestState(pass).label }}
                </StatusBadge>
              </td>
              <td data-label="操作">
                <button v-if="pass.is_active" class="table-action" @click="askRevoke(pass)">
                  撤销
                </button>
                <span v-else class="subtext">—</span>
              </td>
            </tr>
          </tbody>
        </table>
        <EmptyState
          v-else
          :title="loading ? '正在获取访客凭证' : error ? '访客凭证加载失败' : '尚未创建访客凭证'"
          description="为已绑定设备创建临时凭证，交给来访者使用。"
          icon="guests"
        />
      </div>
    </section>
  </div>
  <AppDialog
    v-if="createOpen"
    :title="result ? '访客凭证已创建' : '创建访客凭证'"
    @close="!busy && ((createOpen = false), (result = null))"
  >
    <div class="stack">
      <InlineNotice v-if="mutationError" tone="danger">{{ mutationError }}</InlineNotice>
      <template v-if="result">
        <InlineNotice tone="success">
          凭证已创建。请现在复制，关闭后无法再次查看完整凭证。
        </InlineNotice>
        <div class="secret-code mono">{{ result.pass_code }}</div>
        <p class="subtext">有效期至 {{ serverTime(result.valid_until) }} · 服务器时间</p>
        <button class="button button--primary" @click="copy">
          <AppIcon name="copy" :size="17" />
          {{ copied ? '已复制' : '复制凭证' }}
        </button>
        <RouterLink class="button" to="/guest">打开访客验证页面</RouterLink>
      </template>
      <form v-else class="form-section" @submit.prevent="create">
        <div class="field">
          <label for="guest-device">目标设备</label>
          <select id="guest-device" v-model="form.deviceId" required>
            <option disabled value="">请先绑定设备认证</option>
            <option v-for="item in eligibleDevices" :key="item.device_id" :value="item.device_id">
              {{ item.device_id }}
            </option>
          </select>
          <RouterLink
            v-if="!eligibleDevices.length"
            to="/dashboard/security"
            @click="createOpen = false"
          >
            前往账户与安全绑定设备
          </RouterLink>
        </div>
        <div class="field">
          <label for="guest-name">
            访客名称
            <span class="subtext">（可选）</span>
          </label>
          <input id="guest-name" v-model="form.name" maxlength="80" placeholder="例如：来访同事" />
        </div>
        <div class="form-grid">
          <div class="field">
            <label for="guest-hours">有效时长 · 小时</label>
            <input
              id="guest-hours"
              v-model.number="form.hours"
              type="number"
              min="1"
              max="168"
              step="1"
              required
            />
            <p class="subtext">立即生效，1–168 小时</p>
          </div>
          <div class="field">
            <label for="guest-uses">验证额度 · 次</label>
            <input
              id="guest-uses"
              v-model.number="form.uses"
              type="number"
              min="1"
              max="100"
              step="1"
              required
            />
            <p class="subtext">1–100 次验证</p>
          </div>
        </div>
        <InlineNotice>
          将为 {{ form.deviceId || '所选设备' }} 创建立即生效的凭证，有效
          {{ form.hours }} 小时，可验证 {{ form.uses }} 次。
        </InlineNotice>
        <button class="button button--primary" :disabled="busy || !form.deviceId">
          {{ busy ? '创建中…' : '确认创建' }}
        </button>
      </form>
    </div>
  </AppDialog>
  <AppDialog v-if="revokeTarget" title="撤销访客凭证" @close="!busy && (revokeTarget = null)">
    <div class="stack">
      <p>
        撤销「{{ revokeTarget.guest_name || '未命名访客' }}」在
        {{ revokeTarget.device_id }} 的凭证及相关未完成授权。
      </p>
      <InlineNotice v-if="mutationError" tone="danger">{{ mutationError }}</InlineNotice>
      <div class="button-group">
        <button class="button button--danger" :disabled="busy" @click="revoke">
          {{ busy ? '撤销中…' : '确认撤销' }}
        </button>
        <button class="button" :disabled="busy" @click="revokeTarget = null">返回</button>
      </div>
    </div>
  </AppDialog>
</template>
