<script setup>
import { ref, watch, computed } from 'vue'
import { lock, face } from '../api'
import { useResource } from '../composables/useResource'
import { useDoorSession } from '../composables/useDoorSession'
import { actionLabel, serverTime } from '../domain/presentation'
import PageHeading from '../components/ui/PageHeading.vue'
import InlineNotice from '../components/ui/InlineNotice.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import StatusBadge from '../components/ui/StatusBadge.vue'
import PaginationBar from '../components/ui/PaginationBar.vue'
import AppDialog from '../components/ui/AppDialog.vue'
import PrivateSnapshot from '../components/PrivateSnapshot.vue'
const tab = ref('operations'),
  page = ref(1),
  deviceFilter = ref(''),
  passed = ref(''),
  detail = ref(null)
const { devices } = useDoorSession()
const resource = useResource(
  () =>
    tab.value === 'operations'
      ? lock.getHistory(page.value, 20)
      : face.getLogs(
          page.value,
          20,
          passed.value === '' ? undefined : passed.value,
          deviceFilter.value
        ),
  { data: [], total: 0, pages: 0 }
)
const { data, loading, error } = resource
const rows = computed(() => data.value?.data || [])
function changePage(value) {
  page.value = value
  resource.load()
}
function navigateTabs(event) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  tab.value =
    event.key === 'Home'
      ? 'operations'
      : event.key === 'End'
        ? 'face'
        : tab.value === 'operations'
          ? 'face'
          : 'operations'
  document.getElementById(`${tab.value === 'face' ? 'face' : 'operations'}-tab`).focus()
}
watch(
  [tab, deviceFilter, passed],
  () => {
    page.value = 1
    data.value = { data: [], total: 0, pages: 0 }
    resource.load()
  },
  { immediate: true }
)
</script>
<template>
  <PageHeading
    eyebrow="ACTIVITY & AUDIT"
    title="记录"
    description="操作审计与人脸验证分别查询，命令提交记录不等于执行成功。"
  >
    <button class="button" :disabled="loading" @click="resource.load">刷新记录</button>
  </PageHeading>
  <div class="stack">
    <InlineNotice v-if="error" tone="danger">
      {{ error }}
      <button class="table-action" @click="resource.load">重试</button>
    </InlineNotice>
    <section class="panel">
      <div class="tabs" role="tablist" aria-label="记录类型">
        <button
          id="operations-tab"
          class="tab"
          :class="{ 'tab--active': tab === 'operations' }"
          role="tab"
          :aria-selected="tab === 'operations'"
          :tabindex="tab === 'operations' ? 0 : -1"
          aria-controls="records-panel"
          @keydown="navigateTabs"
          @click="tab = 'operations'"
        >
          操作记录
        </button>
        <button
          id="face-tab"
          class="tab"
          :class="{ 'tab--active': tab === 'face' }"
          role="tab"
          :aria-selected="tab === 'face'"
          :tabindex="tab === 'face' ? 0 : -1"
          aria-controls="records-panel"
          @keydown="navigateTabs"
          @click="tab = 'face'"
        >
          人脸验证
        </button>
      </div>
      <div v-if="tab === 'face'" class="filters">
        <div class="field">
          <label for="record-device">设备</label>
          <select id="record-device" v-model="deviceFilter">
            <option value="">全部可访问设备</option>
            <option v-for="item in devices" :key="item.device_id" :value="item.device_id">
              {{ item.device_id }}
            </option>
          </select>
        </div>
        <div class="field">
          <label for="record-result">验证结果</label>
          <select id="record-result" v-model="passed">
            <option value="">全部结果</option>
            <option value="true">通过</option>
            <option value="false">未通过</option>
          </select>
        </div>
      </div>
      <div v-if="loading" class="loading-line" role="status" aria-label="正在加载记录" />
      <div
        id="records-panel"
        class="table-scroll"
        role="tabpanel"
        :aria-labelledby="tab === 'face' ? 'face-tab' : 'operations-tab'"
        :aria-busy="loading"
      >
        <table v-if="rows.length" class="responsive-table">
          <caption class="sr-only">
            {{ tab === 'operations' ? '操作记录' : '人脸验证记录' }}，时间由服务器提供
          </caption>
          <thead>
            <tr>
              <th>时间 · 服务器时间</th>
              <th>{{ tab === 'operations' ? '用户' : '目标设备' }}</th>
              <th>{{ tab === 'operations' ? '动作' : '验证用户' }}</th>
              <th v-if="tab === 'face'">结果</th>
              <th v-if="tab === 'face'">详情</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td data-label="时间">{{ serverTime(row.timestamp) }}</td>
              <td :data-label="tab === 'operations' ? '用户' : '设备'">
                <span :class="{ mono: tab === 'face' }">
                  {{ tab === 'operations' ? row.username : row.device_id }}
                </span>
              </td>
              <td :data-label="tab === 'operations' ? '动作' : '验证用户'">
                {{
                  tab === 'operations'
                    ? actionLabel(row.action)
                    : row.expected_username || row.face_user_id || '未识别'
                }}
              </td>
              <td v-if="tab === 'face'" data-label="结果">
                <StatusBadge :tone="row.passed ? 'success' : 'danger'">
                  {{ row.passed ? '通过' : '未通过' }}
                </StatusBadge>
              </td>
              <td v-if="tab === 'face'" data-label="详情">
                <button class="table-action" @click="detail = row">查看详情</button>
              </td>
            </tr>
          </tbody>
        </table>
        <EmptyState
          v-else
          :title="loading ? '正在加载记录' : error ? '记录获取失败' : '暂无匹配记录'"
          description="可调整筛选条件或稍后刷新。"
        />
      </div>
      <PaginationBar
        :page="page"
        :pages="data?.pages || 0"
        :total="data?.total || 0"
        :loading="loading"
        @change="changePage"
      />
    </section>
  </div>
  <AppDialog v-if="detail" title="人脸验证详情" @close="detail = null">
    <div class="stack">
      <dl class="detail-list">
        <dt>请求 ID</dt>
        <dd class="mono">{{ detail.request_id }}</dd>
        <dt>设备</dt>
        <dd class="mono">{{ detail.device_id }}</dd>
        <dt>相似度原始值</dt>
        <dd>{{ detail.similarity_score ?? '未提供' }}</dd>
        <dt>失败原因</dt>
        <dd>{{ detail.failure_reason || '无' }}</dd>
      </dl>
      <PrivateSnapshot :path="detail.snapshot || ''" title="验证记录快照" />
    </div>
  </AppDialog>
</template>
