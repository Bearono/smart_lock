<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import AppIcon from './AppIcon.vue'
defineProps({ title: { type: String, required: true }, wide: Boolean })
const emit = defineEmits(['close'])
const element = ref(null)
let previous
onMounted(() => {
  previous = document.activeElement
  element.value.showModal()
})
onBeforeUnmount(() => {
  element.value.close()
  if (previous?.isConnected) previous.focus()
})
</script>
<template>
  <dialog
    ref="element"
    class="app-dialog"
    :class="{ 'app-dialog--wide': wide }"
    :aria-label="title"
    @cancel.prevent="emit('close')"
  >
    <header class="dialog-heading">
      <h2>{{ title }}</h2>
      <button class="icon-button" type="button" aria-label="关闭" @click="emit('close')">
        <AppIcon name="close" />
      </button>
    </header>
    <div class="dialog-content"><slot /></div>
  </dialog>
</template>
