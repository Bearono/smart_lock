<script setup>
import { ref, computed, onMounted } from 'vue'
import { admin, mfa } from '../api'
import { useResource } from '../composables/useResource'
import { useDoorSession } from '../composables/useDoorSession'
import { errorMessage, serverTime } from '../domain/presentation'
import PageHeading from '../components/ui/PageHeading.vue'
import InlineNotice from '../components/ui/InlineNotice.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import StatusBadge from '../components/ui/StatusBadge.vue'
import AppDialog from '../components/ui/AppDialog.vue'
const session = useDoorSession()
const { devices } = session
const filter = ref('pending'),
  search = ref(''),
  selected = ref(null),
  pendingAction = ref(null)
const actionBusy = ref(false),
  actionError = ref(''),
  success = ref(''),
  rowBusy = ref({}),
  grantErrors = ref({})
const users = useResource(() => admin.listUsers(filter.value || undefined), [])
const { data, error, loading } = users
const grants = useResource(async (id) => {
  const response = await admin.userDevices(id)
  return { data: { ...response.data, ownerId: id } }
}, null)
const grantIds = computed(() =>
  grants.data.value?.ownerId === selected.value?.id ? grants.data.value.device_ids || [] : []
)
const grantDevices = computed(() =>
  [...new Set([...devices.value.map((item) => item.device_id), ...grantIds.value])].sort()
)
const visibleUsers = computed(() =>
  data.value.filter((user) => user.username.toLowerCase().includes(search.value.toLowerCase()))
)
const labels = { pending: '待审批', approved: '已批准', rejected: '已拒绝' }
async function select(user) {
  selected.value = user
  grantErrors.value = {}
  await grants.load(user.id)
}
async function setGrant(id, granted) {
  const userId = selected.value?.id
  if (!userId || rowBusy.value[id]) return
  rowBusy.value = { ...rowBusy.value, [id]: true }
  grantErrors.value = { ...grantErrors.value, [id]: '' }
  try {
    await admin.setDeviceGrant(userId, id, granted)
    if (selected.value?.id === userId) await grants.load(userId)
    await session.refreshAuth()
  } catch (failure) {
    if (selected.value?.id === userId) {
      grantErrors.value = {
        ...grantErrors.value,
        [id]: errorMessage(failure, '授权结果未确认，请重新查询')
      }
      await grants.load(userId)
    }
  } finally {
    rowBusy.value = { ...rowBusy.value, [id]: false }
  }
}
function ask(type, user) {
  pendingAction.value = { type, user }
  actionError.value = ''
}
async function perform() {
  if (actionBusy.value) return
  actionBusy.value = true
  actionError.value = ''
  success.value = ''
  const { type, user } = pendingAction.value
  try {
    if (type === 'approve') await admin.approve(user.id)
    else if (type === 'reject') await admin.reject(user.id)
    else await mfa.adminUnlock(user.username)
    pendingAction.value = null
    success.value = '操作已完成'
    if (selected.value?.id === user.id) selected.value = null
    await users.load()
    await session.refreshAuth()
  } catch (failure) {
    actionError.value = errorMessage(failure, '操作结果未确认，请刷新用户信息核查')
  } finally {
    actionBusy.value = false
  }
}
onMounted(users.load)
function changeFilter() {
  selected.value = null
  users.load()
}
</script>
<template>
  <PageHeading
    eyebrow="IDENTITY & PERMISSIONS"
    title="用户与权限"
    description="审批账户并逐设备分配访问权限。"
  >
    <button class="button" :disabled="loading" @click="users.load">刷新用户</button>
  </PageHeading>
  <div class="stack">
    <InlineNotice v-if="error" tone="danger">{{ error }}</InlineNotice>
    <InlineNotice v-if="success" tone="success">{{ success }}</InlineNotice>
    <div class="split-page">
      <section class="panel">
        <div class="filters">
          <div class="field">
            <label for="user-status">账户状态</label>
            <select id="user-status" v-model="filter" @change="changeFilter">
              <option value="">全部状态</option>
              <option value="pending">待审批</option>
              <option value="approved">已批准</option>
              <option value="rejected">已拒绝</option>
            </select>
          </div>
          <div class="field field--search">
            <label for="user-search">搜索当前列表</label>
            <input id="user-search" v-model="search" placeholder="输入用户名" />
          </div>
        </div>
        <div v-if="loading" class="loading-line" />
        <div class="table-scroll">
          <table v-if="visibleUsers.length" class="responsive-table">
            <thead>
              <tr>
                <th>用户</th>
                <th>角色</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in visibleUsers" :key="user.id">
                <td data-label="用户">
                  <div>
                    <strong>{{ user.username }}</strong>
                    <p class="subtext">{{ serverTime(user.created_at) }}</p>
                  </div>
                </td>
                <td data-label="角色">{{ user.role === 'admin' ? '管理员' : '用户' }}</td>
                <td data-label="状态">
                  <StatusBadge
                    :tone="
                      user.status === 'approved'
                        ? 'success'
                        : user.status === 'pending'
                          ? 'warning'
                          : 'neutral'
                    "
                  >
                    {{ labels[user.status] || user.status }}
                  </StatusBadge>
                </td>
                <td data-label="操作">
                  <div class="button-group">
                    <button class="table-action" @click="select(user)">管理权限</button>
                    <button
                      v-if="user.role !== 'admin' && user.status !== 'approved'"
                      class="table-action"
                      @click="ask('approve', user)"
                    >
                      批准
                    </button>
                    <button
                      v-if="user.role !== 'admin' && user.status !== 'rejected'"
                      class="table-action"
                      @click="ask('reject', user)"
                    >
                      拒绝
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <EmptyState
            v-else
            :title="loading ? '正在加载用户' : error ? '用户加载失败' : '暂无匹配用户'"
            icon="users"
          />
        </div>
      </section>
      <section class="panel">
        <template v-if="selected">
          <div class="panel-head">
            <div>
              <h3>{{ selected.username }}</h3>
              <p class="subtext">设备权限与认证限制</p>
            </div>
            <StatusBadge :tone="selected.status === 'approved' ? 'success' : 'neutral'">
              {{ labels[selected.status] }}
            </StatusBadge>
          </div>
          <div class="panel-body stack">
            <InlineNotice v-if="grants.error.value" tone="danger">
              {{ grants.error.value }}
              <button class="table-action" @click="grants.load(selected.id)">重试</button>
            </InlineNotice>
            <p class="subtext">每个设备独立生效。访问授权之后，用户仍需绑定设备认证。</p>
            <div v-if="grants.loading.value" class="loading-line" />
            <template v-if="!grants.loading.value && !grants.error.value">
              <EmptyState v-if="!grantDevices.length" title="暂无已上报或已授权设备" icon="doors" />
              <div
                v-for="id in grantDevices"
                :key="`${selected.id}-${id}`"
                class="stack stack--small"
              >
                <div class="button-group" style="justify-content: space-between">
                  <div>
                    <p class="mono">{{ id }}</p>
                    <p class="subtext">{{ grantIds.includes(id) ? '已授权' : '未授权' }}</p>
                  </div>
                  <button
                    class="button button--small"
                    :disabled="
                      rowBusy[id] || (selected.status !== 'approved' && !grantIds.includes(id))
                    "
                    @click="setGrant(id, !grantIds.includes(id))"
                  >
                    {{ rowBusy[id] ? '提交中…' : grantIds.includes(id) ? '撤销权限' : '授予权限' }}
                  </button>
                </div>
                <InlineNotice v-if="grantErrors[id]" tone="danger">
                  {{ grantErrors[id] }}
                </InlineNotice>
              </div>
            </template>
            <button
              v-if="selected.status !== 'pending'"
              class="button"
              @click="ask('unlock', selected)"
            >
              解除该用户的设备认证锁定
            </button>
          </div>
        </template>
        <EmptyState
          v-else
          title="选择一个用户"
          description="查看设备权限并处理认证限制。"
          icon="users"
        />
      </section>
    </div>
  </div>
  <AppDialog
    v-if="pendingAction"
    :title="
      pendingAction.type === 'approve'
        ? '批准账户'
        : pendingAction.type === 'reject'
          ? '拒绝账户'
          : '解除认证锁定'
    "
    @close="!actionBusy && (pendingAction = null)"
  >
    <div class="stack">
      <p v-if="pendingAction.type === 'approve'">
        批准「{{ pendingAction.user.username }}」的账户？设备访问权限需要另行分配。
      </p>
      <p v-else-if="pendingAction.type === 'reject'">
        拒绝「{{ pendingAction.user.username }}」的账户，将撤销相关访问能力。
      </p>
      <p v-else>
        解除「{{
          pendingAction.user.username
        }}」的设备认证锁定并重置相关失败计数。此操作可能影响该用户的多个设备绑定。
      </p>
      <InlineNotice v-if="actionError" tone="danger">{{ actionError }}</InlineNotice>
      <div class="button-group">
        <button
          class="button"
          :class="pendingAction.type === 'reject' ? 'button--danger' : 'button--primary'"
          :disabled="actionBusy"
          @click="perform"
        >
          {{ actionBusy ? '处理中…' : '确认操作' }}
        </button>
        <button class="button" :disabled="actionBusy" @click="pendingAction = null">返回</button>
      </div>
    </div>
  </AppDialog>
</template>
