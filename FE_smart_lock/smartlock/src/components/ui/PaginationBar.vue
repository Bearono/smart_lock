<script setup>
defineProps({
  page: { type: Number, required: true },
  pages: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
  loading: Boolean
})
const emit = defineEmits(['change'])
</script>
<template>
  <div class="pagination">
    <span class="subtext">共 {{ total }} 条 · 第 {{ page }} / {{ Math.max(1, pages) }} 页</span>
    <div class="button-group">
      <button
        class="button button--small"
        :disabled="loading || page <= 1"
        @click="emit('change', page - 1)"
      >
        上一页
      </button>
      <button
        class="button button--small"
        :disabled="loading || page >= pages"
        @click="emit('change', page + 1)"
      >
        下一页
      </button>
    </div>
  </div>
</template>
