<script setup lang="ts">
defineProps({
  title: { type: String, required: true }
})
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>{{ title }}</h1>
    </div>
    <div class="heading-actions"><slot /></div>
  </div>
</template>
