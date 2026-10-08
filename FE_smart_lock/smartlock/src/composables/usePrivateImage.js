import { ref, onScopeDispose } from 'vue'
import { media } from '../api'
import { errorMessage } from '../domain/presentation'

export function usePrivateImage() {
  const url = ref(''),
    loading = ref(false),
    error = ref('')
  let generation = 0
  function clear() {
    generation++
    if (url.value) URL.revokeObjectURL(url.value)
    url.value = ''
    error.value = ''
    loading.value = false
  }
  async function load(path) {
    clear()
    if (!path) return
    const current = generation
    loading.value = true
    try {
      const response = await media.image(path)
      if (current === generation) url.value = URL.createObjectURL(response.data)
    } catch (failure) {
      if (current === generation) error.value = errorMessage(failure, '图片加载失败，请重试')
    } finally {
      if (current === generation) loading.value = false
    }
  }
  onScopeDispose(clear)
  return { url, loading, error, load, clear }
}
