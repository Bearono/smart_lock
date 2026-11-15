import { ref, watch } from 'vue'

const storageKey = 'smartlock.material-tint'
function readTint() {
  try {
    const saved = localStorage.getItem(storageKey)
    const value = saved === null ? 55 : Number(saved)
    return Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : 55
  } catch {
    return 55
  }
}

export const materialTint = ref(readTint())

export function installAppearance() {
  const minimum =
    Number.parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue('--material-min-opacity')
    ) || 0.65
  const stop = watch(
    materialTint,
    (value) => {
      const tint = Math.min(100, Math.max(0, Number.isFinite(value) ? value : 55))
      document.documentElement.style.setProperty(
        '--material-opacity',
        String(minimum + (tint / 100) * (1 - minimum))
      )
      document.documentElement.dataset.material = tint === 100 ? 'opaque' : 'glass'
      try {
        localStorage.setItem(storageKey, String(tint))
      } catch {
        // Storage restrictions must not prevent navigation or authentication.
      }
    },
    { immediate: true }
  )
  const sync = (event: StorageEvent) => {
    if (event.key === storageKey || event.key === null) materialTint.value = readTint()
  }
  window.addEventListener('storage', sync)
  return () => {
    stop()
    window.removeEventListener('storage', sync)
  }
}
