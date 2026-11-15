import { ref, watch, onScopeDispose } from 'vue'
import type { Ref } from 'vue'
import { media } from '../../shared/api/index.ts'
import { errorMessage } from '../../shared/lib/presentation.js'

/** Own snapshot requests and discard late responses after a device change or unmount. */
export function useSnapshots(selectedId: Ref<string>) {
  const latestPath = ref(''),
    snapshotError = ref(''),
    snapshotBusy = ref(false),
    receivedAt = ref('')
  const clearTarget = ref(''),
    clearing = ref(false)
  let imageGeneration = 0,
    disposed = false,
    snapshotDevice = ''
  async function refreshSnapshot(capture = false) {
    if (capture && snapshotBusy.value) return
    const current = ++imageGeneration,
      id = selectedId.value
    if (snapshotDevice !== id) {
      snapshotDevice = id
      latestPath.value = ''
      receivedAt.value = ''
    }
    snapshotError.value = ''
    snapshotBusy.value = true
    if (!id) {
      snapshotBusy.value = false
      return
    }
    try {
      const response = await (capture ? media.capture(id) : media.latest(id))
      if (!disposed && current === imageGeneration) {
        latestPath.value = response.data.snapshot || ''
        receivedAt.value = response.data.received_at || ''
      }
    } catch (failure) {
      if (!disposed && current === imageGeneration)
        snapshotError.value = errorMessage(
          failure,
          capture ? '拍摄结果未确认，请先刷新已有画面' : '快照信息获取失败'
        )
    } finally {
      if (!disposed && current === imageGeneration) snapshotBusy.value = false
    }
  }
  async function clearSnapshot() {
    if (clearing.value || !clearTarget.value) return
    const target = clearTarget.value
    clearing.value = true
    try {
      await media.clearSnapshot(target)
      if (latestPath.value === target) {
        latestPath.value = ''
        receivedAt.value = ''
      }
      clearTarget.value = ''
      await refreshSnapshot()
    } catch (failure) {
      snapshotError.value = errorMessage(failure, '快照删除结果未确认，请重新获取')
    } finally {
      clearing.value = false
    }
  }
  watch(selectedId, () => refreshSnapshot(), { immediate: true })
  onScopeDispose(() => {
    disposed = true
    imageGeneration++
  })
  return {
    latestPath,
    snapshotError,
    snapshotBusy,
    receivedAt,
    clearTarget,
    clearing,
    refreshSnapshot,
    clearSnapshot
  }
}
