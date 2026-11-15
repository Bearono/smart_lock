<script setup lang="ts">
import { computed } from 'vue'
import { materialTint } from '../../shared/material/appearance.ts'
const finish = computed(() =>
  materialTint.value === 100 ? '纯色' : materialTint.value < 40 ? '通透' : '柔和'
)
</script>
<template>
  <section class="panel appearance-panel" aria-labelledby="appearance-heading">
    <div class="panel-head">
      <h3 id="appearance-heading">显示效果</h3>
      <span class="appearance-value">{{ finish }}</span>
    </div>
    <div class="panel-body stack">
      <div class="field">
        <label for="material-tint">玻璃浓度</label>
        <input
          id="material-tint"
          v-model.number="materialTint"
          type="range"
          min="0"
          max="100"
          step="5"
          :aria-valuetext="`${finish}，${materialTint}%`"
        />
        <div class="appearance-scale" aria-hidden="true">
          <span>通透</span>
          <span>纯色</span>
        </div>
      </div>
    </div>
  </section>
</template>
