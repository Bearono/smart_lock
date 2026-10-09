<script setup lang="ts">
import { ref, computed, watch, onScopeDispose } from 'vue'
import { media, mfa } from '../../shared/api/index.ts'
import { useDoorSession } from '../door/useDoorSession.ts'
import { serverTime, lockState, cameraState, errorMessage } from '../../shared/lib/presentation.js'
import AppIcon from '../../shared/ui/AppIcon.vue'
import AppDialog from '../../shared/ui/AppDialog.vue'
import StatusBadge from '../../shared/ui/StatusBadge.vue'
import InlineNotice from '../../shared/ui/InlineNotice.vue'
import EmptyState from '../../shared/ui/EmptyState.vue'
import RecentActivity from './RecentActivity.vue'
import PrivateSnapshot from '../camera/PrivateSnapshot.vue'
const session = useDoorSession()
const {
  devices,
  selectedId,
  selected,
  refreshing,
  error,
  authStatus,
  authError,
  bound,
  busy,
  phase,
  flowError,
  flowDeviceId,
  flowAction,
  requiresTotp,
  totp,
  taskActive,
  snapshotPath
} = session
const search = ref(''),
  latestPath = ref(''),
  snapshotError = ref(''),
  snapshotBusy = ref(false),
  receivedAt = ref('')
const showList = ref(false)
const clearTarget = ref(''),
  clearing = ref(false)
const visibleDevices = computed(() =>
  devices.value.filter((item) =>
    `${item.display_name || ''} ${item.device_id}`
      .toLowerCase()
      .includes(search.value.toLowerCase())
  )
)
const batteryLabel = computed(() => {
  const battery = selected.value?.battery
  return typeof battery === 'number' && Number.isInteger(battery) && battery >= 0 && battery <= 100
    ? `${battery}%`
    : '未提供'
})

let imageGeneration = 0,
  disposed = false
async function refreshSnapshot() {
  const current = ++imageGeneration,
    id = selectedId.value
  latestPath.value = ''
  receivedAt.value = ''
  snapshotError.value = ''
  snapshotBusy.value = true
  if (!id) {
    snapshotBusy.value = false
    return
  }
  try {
    const response = await media.latest(id)
    if (!disposed && current === imageGeneration) {
      latestPath.value = response.data.snapshot || ''
      receivedAt.value = response.data.received_at || ''
    }
  } catch (failure) {
    if (!disposed && current === imageGeneration)
      snapshotError.value = errorMessage(failure, '快照信息获取失败')
  } finally {
    if (!disposed && current === imageGeneration) snapshotBusy.value = false
  }
}
function changeDevice(event: Event) {
  const element = event.target as HTMLSelectElement
  session.select(element.value)
  element.value = selectedId.value
}
function choose(id: string) {
  if (session.select(id)) showList.value = false
}
async function clearSnapshot() {
  if (clearing.value || !clearTarget.value) return
  clearing.value = true
  try {
    await mfa.clearSnapshot(clearTarget.value)
    clearTarget.value = ''
    await refreshSnapshot()
  } catch (failure) {
    snapshotError.value = errorMessage(failure, '快照删除结果未确认，请重新获取')
  } finally {
    clearing.value = false
  }
}
watch(selectedId, refreshSnapshot, { immediate: true })
onScopeDispose(() => {
  disposed = true
  imageGeneration++
})
</script>
<template>
  <section class="home-welcome">
    <div>
      <p class="eyebrow">HOME, SWEET HOME</p>
      <h1>家的安心，尽在眼前。</h1>
      <p class="subtext">查看家门、门前画面与最近的通行动态。</p>
    </div>
    <div class="button-group welcome-actions">
      <button v-if="devices.length > 1" class="button" @click="showList = !showList">
        <AppIcon name="doors" />
        {{ showList ? '返回门详情' : '设备列表' }}
      </button>
      <button class="button" :disabled="refreshing" @click="session.refresh">
        <AppIcon name="refresh" :size="17" />
        {{ refreshing ? '刷新中' : '刷新状态' }}
      </button>
    </div>
  </section>
  <div class="stack">
    <InlineNotice v-if="error" tone="warning">
      {{ error }}
      <button class="table-action" @click="session.refresh">重新获取</button>
    </InlineNotice>
    <section v-if="!devices.length" class="panel">
      <EmptyState
        :title="refreshing ? '正在获取设备' : error ? '无法获取设备' : '把你的家门连接进来'"
        description="请由管理员授权设备，并让设备完成上报。连接后就能在这里查看家门。"
        icon="doors"
      />
    </section>
    <section v-else-if="showList" class="panel">
      <div class="filters">
        <div class="field field--search">
          <label for="door-search">搜索设备</label>
          <input id="door-search" v-model="search" placeholder="搜索家门名称或设备 ID" />
        </div>
      </div>
      <div class="table-scroll">
        <table v-if="visibleDevices.length" class="responsive-table">
          <thead>
            <tr>
              <th>设备</th>
              <th>连接</th>
              <th>最近锁状态</th>
              <th>摄像头</th>
              <th>最近上报 · 服务器时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in visibleDevices" :key="item.device_id">
              <td data-label="设备">
                <strong class="mono">{{ item.display_name || item.device_id }}</strong>
              </td>
              <td data-label="连接">
                <StatusBadge :tone="item.is_online ? 'success' : 'neutral'">
                  {{ item.is_online ? '在线' : '离线' }}
                </StatusBadge>
              </td>
              <td data-label="锁状态">{{ lockState(item.reported_status) }}</td>
              <td data-label="摄像头">{{ cameraState(item.camera_status) }}</td>
              <td data-label="最近上报">{{ serverTime(item.last_update) }}</td>
              <td data-label="操作">
                <button class="table-action" :disabled="taskActive" @click="choose(item.device_id)">
                  查看详情 →
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <EmptyState v-else title="没有匹配设备" description="尝试其他设备 ID。" />
      </div>
    </section>
    <template v-else-if="selected">
      <div class="door-summary">
        <div class="field" style="min-width: 200px">
          <label for="device-select" class="sr-only">当前设备</label>
          <select
            id="device-select"
            :value="selectedId"
            :disabled="taskActive"
            @change="changeDevice"
          >
            <option v-for="item in devices" :key="item.device_id" :value="item.device_id">
              {{ item.display_name || item.device_id }}
            </option>
          </select>
        </div>
        <StatusBadge :tone="error ? 'warning' : selected.is_online ? 'success' : 'neutral'">
          {{ error ? '连接信息待更新' : selected.is_online ? '在线' : '离线' }}
        </StatusBadge>
        <span class="subtext">最近上报：{{ serverTime(selected.last_update) }}</span>
      </div>
      <div class="door-grid">
        <section class="panel">
          <div class="panel-head">
            <div>
              <h3>门前画面</h3>
              <p class="subtext">最近收到的快照 · 轻点图片查看大图</p>
            </div>
            <button
              class="icon-button"
              aria-label="刷新快照"
              :disabled="snapshotBusy"
              @click="refreshSnapshot"
            >
              <AppIcon name="refresh" :size="17" />
            </button>
          </div>
          <InlineNotice v-if="snapshotError" tone="warning">{{ snapshotError }}</InlineNotice>
          <div v-if="snapshotBusy" class="loading-line" role="status" aria-label="正在获取快照" />
          <PrivateSnapshot :path="latestPath" />
          <p class="snapshot-caption subtext">
            {{ receivedAt ? `服务器接收时间：${serverTime(receivedAt)}` : '尚无快照接收时间' }} ·
            非实时视频
          </p>
          <div v-if="latestPath" class="panel-body" style="padding-top: 12px; padding-bottom: 12px">
            <button class="table-action" @click="clearTarget = latestPath">删除此快照</button>
          </div>
          <div class="status-grid">
            <div>
              <span class="subtext">摄像头</span>
              <p>{{ cameraState(selected.camera_status) }}</p>
            </div>
            <div>
              <span class="subtext">电量</span>
              <p>{{ batteryLabel }}</p>
            </div>
            <div>
              <span class="subtext">设备 ID</span>
              <p class="mono">{{ selected.device_id }}</p>
            </div>
          </div>
        </section>
        <section class="panel door-controls">
          <div class="panel-head">
            <h3>家门守护</h3>
            <AppIcon name="shield" :size="18" />
          </div>
          <div class="panel-body">
            <p class="subtext">门锁最近状态</p>
            <div class="lock-hero" :data-state="selected.reported_status">
              <AppIcon name="lock" :size="40" />
              <div>
                <strong>{{ lockState(selected.reported_status) }}</strong>
                <span class="subtext">
                  {{ selected.is_online ? '依据设备上报' : '设备离线，此为历史上报' }}
                </span>
              </div>
            </div>
            <div class="stack stack--small">
              <InlineNotice v-if="authError" tone="warning">
                {{ authError }}
                <button class="table-action" @click="session.refreshAuth">重试</button>
              </InlineNotice>
              <p v-else-if="!authStatus" class="subtext">正在检查认证准备情况…</p>
              <p v-else class="subtext">
                {{ bound ? '设备认证已绑定，开门仍需身份验证。' : '请先完成该设备的认证绑定。' }}
              </p>
              <RouterLink
                v-if="authStatus && !bound"
                class="button button--primary"
                to="/dashboard/security"
              >
                设置设备认证
                <AppIcon name="arrow" :size="16" />
              </RouterLink>
              <button
                v-else
                class="button button--primary button--block"
                :disabled="taskActive || !bound || !!error || !selected.is_online"
                @click="session.startFace"
              >
                <AppIcon name="shield" :size="18" />
                {{ busy && phase === 'face' ? '正在验证人脸…' : '验证并开门' }}
              </button>
              <button
                class="button button--block"
                :disabled="taskActive || !bound || !!error || !selected.is_online"
                @click="session.requestLock"
              >
                <AppIcon name="lock" :size="17" />
                上锁
              </button>
              <p v-if="taskActive" class="subtext">
                当前任务进行中，请先完成验证或确认原命令结果。
              </p>
              <p v-else-if="!selected.is_online" class="subtext">设备离线，连接恢复后可操作。</p>
              <RouterLink class="subtext" to="/dashboard/security">认证与设置 →</RouterLink>
            </div>
          </div>
        </section>
      </div>
      <RecentActivity :device-id="selectedId" :refresh-signal="`${phase}:${refreshing}`" />
    </template>
    <section v-if="['face', 'confirm', 'recover', 'failed'].includes(phase)" class="panel">
      <div class="panel-head">
        <div>
          <h3>{{ flowAction === '开门' ? '开门验证' : '上锁操作' }}</h3>
          <p class="subtext mono">目标设备：{{ flowDeviceId }}</p>
        </div>
      </div>
      <div v-if="busy" class="loading-line" />
      <div class="panel-body">
        <div v-if="flowAction === '开门'" class="steps" aria-label="认证步骤">
          <div class="step step--active">01 · 人脸验证</div>
          <div class="step" :class="{ 'step--active': ['confirm', 'recover'].includes(phase) }">
            02 · 确认身份
          </div>
          <div class="step">03 · 执行确认</div>
        </div>
        <div class="stack">
          <InlineNotice v-if="flowError" :tone="phase === 'failed' ? 'danger' : 'warning'">
            {{ flowError }}
          </InlineNotice>
          <p v-if="phase === 'face'">正在进行人脸验证，请面向设备摄像头。</p>
          <PrivateSnapshot v-if="snapshotPath" :path="snapshotPath" title="本次验证快照" />
          <form v-if="phase === 'confirm'" class="form-section" @submit.prevent="session.confirm">
            <div v-if="requiresTotp" class="field" style="max-width: 320px">
              <label for="door-totp">身份验证器验证码</label>
              <input
                id="door-totp"
                v-model="totp"
                inputmode="numeric"
                autocomplete="one-time-code"
                maxlength="6"
                pattern="[0-9]{6}"
                placeholder="六位验证码"
                required
                :disabled="busy"
              />
            </div>
            <p v-else class="subtext">确认后将提交开门命令，执行结果会独立显示。</p>
            <div class="button-group">
              <button class="button button--primary" :disabled="busy">
                {{ busy ? '正在提交…' : '确认并提交开门' }}
              </button>
              <button type="button" class="button" :disabled="busy" @click="session.resetFlow">
                结束本次验证
              </button>
            </div>
          </form>
          <div v-if="phase === 'recover'" class="button-group">
            <button class="button button--primary" :disabled="busy" @click="session.confirm">
              {{ busy ? '恢复中…' : '恢复原命令结果' }}
            </button>
            <span class="subtext">不会重新签发访客或认证凭证。</span>
          </div>
          <button
            v-if="phase === 'failed'"
            class="button"
            style="align-self: start"
            @click="session.resetFlow"
          >
            返回家门守护
          </button>
        </div>
      </div>
    </section>
  </div>
  <AppDialog v-if="clearTarget" title="删除此快照" @close="!clearing && (clearTarget = '')">
    <div class="stack">
      <p>删除当前快照后，记录中引用此图片的预览可能无法显示。</p>
      <InlineNotice v-if="snapshotError" tone="danger">{{ snapshotError }}</InlineNotice>
      <button class="button button--danger" :disabled="clearing" @click="clearSnapshot">
        {{ clearing ? '正在删除…' : '确认删除' }}
      </button>
    </div>
  </AppDialog>
</template>
