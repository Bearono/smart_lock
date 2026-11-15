<script setup lang="ts">
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' }
})
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>{{ title }}</h1>
      <p v-if="description" class="subtext">{{ description }}</p>
    </div>
    <div class="heading-actions"><slot /></div>
  </div>
</template>
