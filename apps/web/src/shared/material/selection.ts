import { nextTick, onMounted, onBeforeUnmount, watch, type Ref } from 'vue'
import { advanceSpring, springSettled } from './spring.js'

// A single selection lens travels between destinations. Link geometry and hit
// targets stay unchanged; only the decorative layer moves.
export function useFloatingSelection(element: Ref<HTMLElement | null>, route: () => string) {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)')
  const current = ['x', 'y', 'w', 'h'].map(() => ({ position: 0, velocity: 0 }))
  let target = [0, 0, 0, 0]
  let frame = 0,
    previous = 0,
    initialized = false
  let observer: ResizeObserver | null = null
  function paint() {
    const nav = element.value
    if (!nav) return
    for (const [index, key] of ['x', 'y', 'w', 'h'].entries()) {
      nav.style.setProperty(`--selection-${key}`, `${current[index].position}px`)
    }
  }
  function finish() {
    cancelAnimationFrame(frame)
    frame = 0
    previous = 0
    current.forEach((state, index) => {
      state.position = target[index]
      state.velocity = 0
    })
    paint()
  }
  function tick(now: number) {
    const elapsed = previous ? (now - previous) / 1000 : 1 / 60
    previous = now
    current.forEach((state, index) =>
      Object.assign(state, advanceSpring(state, target[index], elapsed))
    )
    paint()
    if (current.every((state, index) => springSettled(state, target[index]))) finish()
    else frame = requestAnimationFrame(tick)
  }
  function measure() {
    const nav = element.value
    const active = nav?.querySelector<HTMLElement>('a[aria-current="page"]')
    if (!nav) return
    nav.dataset.selection = ''
    nav.style.setProperty('--selection-opacity', active ? '1' : '0')
    if (!active) {
      finish()
      initialized = false
      return
    }
    target = [active.offsetLeft, active.offsetTop, active.offsetWidth, active.offsetHeight]
    if (!initialized || reduced.matches || document.hidden) {
      finish()
      initialized = true
    } else if (!frame) frame = requestAnimationFrame(tick)
  }
  watch(route, () => nextTick(measure), { flush: 'post' })
  onMounted(() => {
    measure()
    observer = new ResizeObserver(measure)
    if (element.value) observer.observe(element.value)
    reduced.addEventListener('change', measure)
  })
  onBeforeUnmount(() => {
    observer?.disconnect()
    reduced.removeEventListener('change', measure)
    cancelAnimationFrame(frame)
  })
}
