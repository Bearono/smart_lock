<script setup lang="ts">
import { watch } from 'vue'
import type { Activity } from '../../shared/api/records'
import { lock } from '../../shared/api/index.ts'
import { useResource } from '../../shared/lib/useResource.ts'
import { actionLabel, serverTime } from '../../shared/lib/presentation.js'
import AppIcon from '../../shared/ui/AppIcon.vue'
import InlineNotice from '../../shared/ui/InlineNotice.vue'
const props = defineProps<{ deviceId: string; refreshSignal: string }>()
const resource = useResource<{ data: Activity[] }>(
  async () => {
    const response = await lock.getHistory(1, 4, props.deviceId)
    if (!Array.isArray(response.data?.data)) throw new Error('动态数据格式不正确')
    return response
  },
  { data: [] }
)
const { data, loading, error } = resource
watch(
  () => props.deviceId,
  () => {
    data.value = { data: [] }
    resource.load()
  },
  { immediate: true }
)
watch(
  () => props.refreshSignal,
  () => resource.load()
)
</script>
<template>
  <section class="panel recent-activity">
    <div class="panel-head">
      <div>
        <h3>最近动态</h3>
        <p class="subtext">当前家门的操作记录</p>
      </div>
      <RouterLink
        :to="{ path: '/dashboard/records', query: { device_id: deviceId } }"
        class="activity-link"
      >
        查看全部
        <AppIcon name="arrow" :size="16" />
      </RouterLink>
    </div>
    <InlineNotice v-if="error" tone="warning">
      {{ error }}
      <button class="table-action" @click="resource.load">重试</button>
    </InlineNotice>
    <div v-if="loading" class="loading-line" role="status" aria-label="正在获取最近动态" />
    <div v-if="data.data.length" class="recent-rows">
      <div v-for="item in data.data" :key="item.id" class="recent-row">
        <span class="event-icon"><AppIcon name="records" :size="19" /></span>
        <div>
          <strong>{{ actionLabel(item.action) }}</strong>
          <p class="subtext">
            {{ item.username || '未记录操作者' }} · {{ serverTime(item.timestamp) }}
          </p>
        </div>
        <span class="recent-kind">操作审计</span>
      </div>
    </div>
    <div v-else-if="!loading && !error" class="recent-empty">
      <AppIcon name="clock" :size="21" />
      <span>还没有这扇家门的操作记录。</span>
    </div>
  </section>
</template>
