<script setup>
import { ref, watch } from 'vue'
import { alarm } from '../api'
import { useResource } from '../composables/useResource'
import { errorMessage, serverTime } from '../domain/presentation'
import PageHeading from '../components/ui/PageHeading.vue'
import InlineNotice from '../components/ui/InlineNotice.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import StatusBadge from '../components/ui/StatusBadge.vue'
import AppDialog from '../components/ui/AppDialog.vue'
import PrivateSnapshot from '../components/PrivateSnapshot.vue'
const filter = ref('pending'),
  detail = ref(null),
  busy = ref(false),
  mutationError = ref('')
const labels = { pending: '待处理', resolved: '已解决', ignored: '已忽略' }
const emailLabels = {
  pending: '等待发送',
  sent: '已发送',
  failed: '发送失败',
  disabled: '未启用',
  queued: '已入队'
}
const resource = useResource(() => alarm.list(filter.value || undefined, 100), [])
const { data, loading, error } = resource
watch(filter, resource.load, { immediate: true })
async function update(status) {
  if (busy.value || !detail.value) return
  busy.value = true
  mutationError.value = ''
  try {
    await alarm.update(detail.value.id, status)
    detail.value = null
    await resource.load()
  } catch (failure) {
    mutationError.value = errorMessage(failure, '处理结果未确认，请刷新列表核查')
  } finally {
    busy.value = false
  }
}
function openDetail(item) {
  detail.value = item
  mutationError.value = ''
}
</script>
<template>
  <PageHeading
    eyebrow="INCIDENT MANAGEMENT"
    title="报警"
    description="查看安全事件并记录处理结果。"
  >
    <button class="button" :disabled="loading" @click="resource.load">刷新报警</button>
  </PageHeading>
  <div class="stack">
    <InlineNotice v-if="error" tone="danger">{{ error }}</InlineNotice>
    <section class="panel">
      <div class="filters">
        <div class="field">
          <label for="alarm-status">处理状态</label>
          <select id="alarm-status" v-model="filter">
            <option value="">全部状态</option>
            <option value="pending">待处理</option>
            <option value="resolved">已解决</option>
            <option value="ignored">已忽略</option>
          </select>
        </div>
        <p class="subtext">当前筛选最近最多 100 条 · 服务器时间</p>
      </div>
      <div v-if="loading" class="loading-line" />
      <div class="table-scroll">
        <table v-if="data.length" class="responsive-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>类型</th>
              <th>消息</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in data" :key="item.id">
              <td data-label="时间">{{ serverTime(item.time) }}</td>
              <td data-label="类型">{{ item.type }}</td>
              <td data-label="消息" style="max-width: 420px">{{ item.message }}</td>
              <td data-label="状态">
                <StatusBadge
                  :tone="
                    item.status === 'pending'
                      ? 'warning'
                      : item.status === 'resolved'
                        ? 'success'
                        : 'neutral'
                  "
                >
                  {{ labels[item.status] || item.status }}
                </StatusBadge>
              </td>
              <td data-label="操作">
                <button class="table-action" @click="openDetail(item)">查看与处理</button>
              </td>
            </tr>
          </tbody>
        </table>
        <EmptyState
          v-else
          :title="
            loading
              ? '正在加载报警'
              : error
                ? '报警加载失败'
                : filter === 'pending'
                  ? '当前没有待处理报警'
                  : '暂无匹配报警'
          "
          icon="alarms"
        />
      </div>
    </section>
  </div>
  <AppDialog v-if="detail" title="报警详情" @close="!busy && (detail = null)">
    <div class="stack">
      <StatusBadge :tone="detail.status === 'pending' ? 'warning' : 'neutral'">
        {{ labels[detail.status] || detail.status }}
      </StatusBadge>
      <p>{{ detail.message }}</p>
      <dl class="detail-list">
        <dt>类型</dt>
        <dd>{{ detail.type }}</dd>
        <dt>发生时间</dt>
        <dd>{{ serverTime(detail.time) }}</dd>
        <dt>处理人</dt>
        <dd>{{ detail.handled_by || '尚未处理' }}</dd>
        <dt>处理时间</dt>
        <dd>{{ serverTime(detail.handled_at) }}</dd>
        <dt>邮件通知</dt>
        <dd>{{ emailLabels[detail.email_status] || detail.email_status || '未提供' }}</dd>
      </dl>
      <PrivateSnapshot v-if="detail.snapshot" :path="detail.snapshot" title="报警快照" />
      <InlineNotice v-if="mutationError" tone="danger">{{ mutationError }}</InlineNotice>
      <div class="button-group">
        <button
          v-if="detail.status !== 'resolved'"
          class="button button--primary"
          :disabled="busy"
          @click="update('resolved')"
        >
          标记已解决
        </button>
        <button
          v-if="detail.status !== 'ignored'"
          class="button"
          :disabled="busy"
          @click="update('ignored')"
        >
          忽略此报警
        </button>
        <button
          v-if="detail.status !== 'pending'"
          class="button"
          :disabled="busy"
          @click="update('pending')"
        >
          重新待处理
        </button>
      </div>
    </div>
  </AppDialog>
</template>
