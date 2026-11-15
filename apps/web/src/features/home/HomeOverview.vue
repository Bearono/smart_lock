<script setup lang="ts">
import { computed } from 'vue'
import type { Device } from '../../shared/api/contracts.ts'
import AppIcon from '../../shared/ui/AppIcon.vue'

const props = defineProps<{ devices: Device[]; stale: boolean }>()
const connected = computed(() => props.devices.filter((item) => item.is_online).length)
const cameras = computed(
  () => props.devices.filter((item) => item.is_online && item.camera_status === 'ONLINE').length
)
</script>
<template>
  <dl class="home-overview" aria-label="设备概览">
    <div class="overview-item">
      <span class="overview-icon"><AppIcon name="doors" :size="21" /></span>
      <div>
        <dt>已添加设备</dt>
        <dd>
          {{ devices.length }}
          <span>台</span>
        </dd>
      </div>
    </div>
    <div class="overview-item">
      <span class="overview-icon overview-icon--connection">
        <AppIcon name="check" :size="21" />
      </span>
      <div>
        <dt>当前在线</dt>
        <dd>
          {{ stale ? '待更新' : connected }}
          <span v-if="!stale">台</span>
        </dd>
      </div>
    </div>
    <div class="overview-item">
      <span class="overview-icon overview-icon--camera"><AppIcon name="camera" :size="21" /></span>
      <div>
        <dt>摄像头就绪</dt>
        <dd>
          {{ stale ? '待更新' : cameras }}
          <span v-if="!stale">台</span>
        </dd>
      </div>
    </div>
  </dl>
</template>
