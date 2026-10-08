<script setup lang="ts">
import { ref, watch } from 'vue'
import { usePrivateImage } from './usePrivateImage.js'
import EmptyState from '../../shared/ui/EmptyState.vue'
import AppDialog from '../../shared/ui/AppDialog.vue'
const props = defineProps({
  path: { type: String, default: '' },
  title: { type: String, default: '最新可用快照' }
})
const { url, error, loading, load } = usePrivateImage()
const expanded = ref(false)
watch(
  () => props.path,
  (path) => {
    expanded.value = false
    load(path)
  },
  { immediate: true }
)
</script>
<template>
  <div class="snapshot-surface" :aria-busy="loading">
    <button
      v-if="url"
      class="snapshot-button"
      :aria-label="`放大${title}`"
      @click="expanded = true"
    >
      <img :src="url" :alt="title" />
      <span class="snapshot-expand">查看大图 ↗</span>
    </button>
    <EmptyState
      v-else
      :title="loading ? '正在加载快照' : error ? '快照加载失败' : '暂无可用快照'"
      :description="error || (loading ? '正在获取授权图片' : '设备上传图片后将在此显示')"
      icon="camera"
    >
      <button v-if="error" class="button button--small" @click="load(path)">重新加载</button>
    </EmptyState>
  </div>
  <AppDialog v-if="expanded" :title="title" wide @close="expanded = false">
    <img class="expanded-image" :src="url" :alt="title" />
  </AppDialog>
</template>
