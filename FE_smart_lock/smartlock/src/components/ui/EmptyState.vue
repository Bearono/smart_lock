<script setup>
import AppIcon from './AppIcon.vue'
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  icon: { type: String, default: 'records' }
})
</script>
<template>
  <div class="empty-state">
    <div class="empty-icon"><AppIcon :name="icon" :size="26" /></div>
    <h3>{{ title }}</h3>
    <p v-if="description">{{ description }}</p>
    <slot />
  </div>
</template>
