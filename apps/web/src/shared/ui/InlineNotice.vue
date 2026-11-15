<script setup lang="ts">
import AppIcon from './AppIcon.vue'
defineProps({ tone: { type: String, default: 'info' } })
</script>
<template>
  <div class="notice" :class="`notice--${tone}`" :role="tone === 'danger' ? 'alert' : 'status'">
    <AppIcon name="info" :size="18" />
    <div><slot /></div>
  </div>
</template>
