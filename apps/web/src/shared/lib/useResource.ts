import { shallowRef, ref, onScopeDispose } from 'vue'
import { errorMessage } from './presentation.js'

/** Each load owns its result. Late responses cannot replace a newer selection. */
export function useResource<T, Args extends unknown[] = []>(
  fetcher: (...args: Args) => Promise<{ data: T }>,
  initial: T
) {
  const data = shallowRef<T>(initial),
    loading = ref(false),
    error = ref('')
  let generation = 0
  async function load(...args: Args) {
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
