import { advanceSpring, springSettled } from './spring.js'

type Spring = { position: number; velocity: number; target: number }
const controls =
  '.button, .icon-button, .nav-link, .management-navigation a, .auth-links button, .tab'

export function installFeedback() {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)')
  const abort = new AbortController()
  const options = { signal: abort.signal, passive: true }
  const springs = new Map<HTMLElement, Spring>()
  const pointers = new Map<number, HTMLElement>()
  const heldKeys = new Map<string, HTMLElement>()
  const glows = new Set<HTMLElement>()
  let pendingGlow: PointerEvent | null = null
  let frame = 0,
    previous = 0

  function tick(now: number) {
    const elapsed = previous ? (now - previous) / 1000 : 1 / 60
    previous = now
    if (pendingGlow) {
      renderGlow(pendingGlow)
      pendingGlow = null
    }
    for (const [element, spring] of springs) {
      if (!element.isConnected || reduced.matches) {
        element.style.removeProperty('--press-scale')
        springs.delete(element)
        continue
      }
      Object.assign(spring, advanceSpring(spring, spring.target, elapsed))
      element.style.setProperty(
        '--press-scale',
        String(Math.max(0.9, Math.min(1.045, spring.position)))
      )
      if (springSettled(spring, spring.target)) {
        if (spring.target === 1) element.style.removeProperty('--press-scale')
        springs.delete(element)
      }
    }
    frame = springs.size ? requestAnimationFrame(tick) : 0
    if (!frame) previous = 0
  }
  function animate(element: HTMLElement, target: number, impulse = 0) {
    if (reduced.matches) return
    const spring = springs.get(element) || {
      position: Number(element.style.getPropertyValue('--press-scale')) || 1,
      velocity: 0,
      target
    }
    spring.target = target
    spring.velocity += impulse
    springs.set(element, spring)
    if (!frame) frame = requestAnimationFrame(tick)
  }
  function control(event: Event) {
    const element =
      event.target instanceof Element ? event.target.closest<HTMLElement>(controls) : null
    if (!element?.closest('#app') || element.matches(':disabled, [aria-disabled="true"]'))
      return null
    return element
  }
  function glow(event: PointerEvent) {
    if (reduced.matches) return
    pendingGlow = event
    if (!frame) frame = requestAnimationFrame(tick)
  }
  function renderGlow(event: PointerEvent) {
    if (!(event.target instanceof Element)) return
    const surface = event.target.closest<HTMLElement>('[data-glass]')
    for (const previous of glows) {
      if (previous !== surface) {
        previous.style.removeProperty('--glass-light')
        glows.delete(previous)
      }
    }
    if (!surface) return
    const box = surface.getBoundingClientRect()
    surface.style.setProperty('--glass-x', `${event.clientX - box.left}px`)
    surface.style.setProperty('--glass-y', `${event.clientY - box.top}px`)
    surface.style.setProperty('--glass-light', event.buttons ? '0.85' : '0.45')
    glows.add(surface)
  }
  function clearGlows() {
    pendingGlow = null
    for (const surface of glows) surface.style.removeProperty('--glass-light')
    glows.clear()
  }
  function release(pointer: number, bounce = true) {
    const element = pointers.get(pointer)
    if (element) animate(element, 1, bounce ? 1.7 : 0)
    pointers.delete(pointer)
    clearGlows()
  }
  function reset() {
    for (const element of springs.keys()) element.style.removeProperty('--press-scale')
    for (const element of pointers.values()) element.style.removeProperty('--press-scale')
    springs.clear()
    pointers.clear()
    heldKeys.clear()
    clearGlows()
    cancelAnimationFrame(frame)
    frame = 0
    previous = 0
  }
  document.addEventListener(
    'pointerdown',
    (event) => {
      if (event.button !== 0) return
      const element = control(event)
      if (element) {
        pointers.set(event.pointerId, element)
        animate(element, 0.945, -0.6)
      }
      glow(event)
    },
    options
  )
  document.addEventListener('pointermove', glow, options)
  document.addEventListener('pointerup', (event) => release(event.pointerId), options)
  document.addEventListener('pointercancel', (event) => release(event.pointerId, false), options)
  document.addEventListener(
    'pointerout',
    (event) => {
      if (!(event.relatedTarget instanceof Node)) clearGlows()
    },
    options
  )
  document.addEventListener(
    'keydown',
    (event) => {
      if (!['Enter', ' '].includes(event.key) || event.repeat) return
      const element = control(event)
      if (element) {
        heldKeys.set(event.key, element)
        animate(element, 0.945, -0.6)
      }
    },
    options
  )
  document.addEventListener(
    'keyup',
    (event) => {
      const element = heldKeys.get(event.key)
      if (element) animate(element, 1, 1.7)
      heldKeys.delete(event.key)
    },
    options
  )
  document.addEventListener(
    'visibilitychange',
    () => {
      if (document.hidden) reset()
    },
    options
  )
  window.addEventListener('blur', reset, options)
  reduced.addEventListener('change', reset, options)
  return () => {
    reset()
    abort.abort()
  }
}

export function playDialogEntry(element: HTMLDialogElement) {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const frames: Keyframe[] = []
  let state = { position: 0, velocity: 0 }
  for (let index = 0; index <= 60; index++) {
    frames.push({
      offset: index / 60,
      opacity: Math.min(1, Math.max(0, state.position * 1.5)),
      transform: `translateY(${(1 - state.position) * 18}px) scale(${0.96 + state.position * 0.04})`
    })
    state = advanceSpring(state, 1, 1 / 120)
  }
  element.animate(frames, { duration: 500, easing: 'linear' })
}
