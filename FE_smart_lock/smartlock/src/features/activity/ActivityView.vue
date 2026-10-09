<script setup lang="ts">
import type { Activity } from '../../shared/api/records'
import { ref, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { lock, face } from '../../shared/api/index.ts'
import { useResource } from '../../shared/lib/useResource.ts'
import { useDoorSession } from '../door/useDoorSession.ts'
import { actionLabel, serverTime } from '../../shared/lib/presentation.js'
import PageHeading from '../../shared/ui/PageHeading.vue'
import InlineNotice from '../../shared/ui/InlineNotice.vue'
import EmptyState from '../../shared/ui/EmptyState.vue'
import StatusBadge from '../../shared/ui/StatusBadge.vue'
import PaginationBar from '../../shared/ui/PaginationBar.vue'
import AppDialog from '../../shared/ui/AppDialog.vue'
import PrivateSnapshot from '../camera/PrivateSnapshot.vue'
const route = useRoute()
const tab = ref('operations'),
  page = ref(1),
  deviceFilter = ref(typeof route.query.device_id === 'string' ? route.query.device_id : ''),
  passed = ref(''),
  detail = ref<Activity | null>(null)
const { devices } = useDoorSession()
const resource = useResource<{ data: Activity[]; total: number; pages: number }>(
  () =>
    tab.value === 'operations'
      ? lock.getHistory(page.value, 20, deviceFilter.value)
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
function changePage(value: number) {
  page.value = value
  resource.load()
}
function navigateTabs(event: KeyboardEvent) {
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
  document.getElementById(`${tab.value === 'face' ? 'face' : 'operations'}-tab`)?.focus()
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
    eyebrow="家门的每一次动态"
    title="家门动态"
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
      <div class="filters">
        <div class="field">
          <label for="record-device">设备</label>
          <select id="record-device" v-model="deviceFilter">
            <option value="">全部可访问设备</option>
            <option v-for="item in devices" :key="item.device_id" :value="item.device_id">
              {{ item.display_name || item.device_id }}
            </option>
          </select>
        </div>
        <div v-if="tab === 'face'" class="field">
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
        <ol v-if="rows.length" class="activity-feed" aria-label="家门动态">
          <li v-for="(row, index) in rows" :key="row.id">
            <p
              v-if="
                index === 0 ||
                rows[index - 1].timestamp?.slice(0, 10) !== row.timestamp?.slice(0, 10)
              "
              class="activity-date"
            >
              {{ row.timestamp?.slice(0, 10) || '日期未提供' }}
            </p>
            <article class="activity-event">
              <span class="activity-marker" aria-hidden="true">
                {{ tab === 'operations' ? '↗' : '◎' }}
              </span>
              <div class="activity-copy">
                <h3>
                  {{
                    tab === 'operations'
                      ? actionLabel(row.action)
                      : row.passed
                        ? '人脸验证通过'
                        : '人脸验证未通过'
                  }}
                </h3>
                <p class="subtext">
                  {{ row.username || row.expected_username || row.face_user_id || '人员未提供' }} ·
                  {{ row.device_id || '历史记录未关联设备' }}
                </p>
                <time class="subtext">{{ serverTime(row.timestamp) }}</time>
                <p v-if="row.command_id" class="subtext mono">命令 {{ row.command_id }}</p>
              </div>
              <template v-if="tab === 'face'">
                <StatusBadge :tone="row.passed ? 'success' : 'danger'">
                  {{ row.passed ? '通过' : '未通过' }}
                </StatusBadge>
                <button class="table-action" @click="detail = row">查看详情</button>
              </template>
            </article>
          </li>
        </ol>
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
