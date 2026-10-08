import { ref, onScopeDispose } from 'vue'
import { errorMessage } from '../domain/presentation'

// A generation owns the result, including A → B → A navigation and unmounts.
export function useResource(fetcher, initial = null) {
  const data = ref(initial),
    loading = ref(false),
    error = ref('')
  let generation = 0
  async function load(...args) {
    const current = ++generation
    loading.value = true
    error.value = ''
    try {
      const response = await fetcher(...args)
      if (current === generation) data.value = response.data
      return response.data
    } catch (failure) {
      if (current === generation) error.value = errorMessage(failure, '数据加载失败，请重试')
    } finally {
      if (current === generation) loading.value = false
    }
  }
  onScopeDispose(() => {
    generation++
  })
  return { data, loading, error, load }
}
