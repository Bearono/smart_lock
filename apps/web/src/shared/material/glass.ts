import type { App, ObjectDirective } from 'vue'
import { lensMap } from './optics.js'
import { installFeedback } from './interaction.ts'
import { installAppearance } from './appearance.ts'

let sequence = 0
const dispose = new WeakMap<HTMLElement, () => void>()
const svgNS = 'http://www.w3.org/2000/svg'

type GlassFinish = 'clear' | 'regular'

function opticalLayer(element: HTMLElement, finish: GlassFinish) {
  element.dataset.glass = ''
  if (!CSS.supports('backdrop-filter', 'url("#glass-test")'))
    return () => element.removeAttribute('data-glass')
  const id = `smartlock-lens-${++sequence}`
  const svg = document.createElementNS(svgNS, 'svg')
  svg.setAttribute('width', '0')
  svg.setAttribute('height', '0')
  svg.setAttribute('aria-hidden', 'true')
  svg.style.position = 'absolute'
  svg.style.pointerEvents = 'none'
  const defs = document.createElementNS(svgNS, 'defs')
  const filter = document.createElementNS(svgNS, 'filter')
  for (const [key, value] of Object.entries({
    id,
    x: '0',
    y: '0',
    width: '100%',
    height: '100%',
    'color-interpolation-filters': 'sRGB'
  }))
    filter.setAttribute(key, value)
  const blur = document.createElementNS(svgNS, 'feGaussianBlur')
  blur.setAttribute('in', 'SourceGraphic')
  blur.setAttribute('stdDeviation', finish === 'clear' ? '3' : '10')
  blur.setAttribute('edgeMode', 'duplicate')
  blur.setAttribute('result', 'soft')
  const map = document.createElementNS(svgNS, 'feImage')
  for (const [key, value] of Object.entries({
    x: '0',
    y: '0',
    width: '100%',
    height: '100%',
    preserveAspectRatio: 'none',
    result: 'normal'
  }))
    map.setAttribute(key, value)
  const lens = document.createElementNS(svgNS, 'feDisplacementMap')
  const refraction = finish === 'clear' ? 24 : 16
  for (const [key, value] of Object.entries({
    in: 'soft',
    in2: 'normal',
    scale: String(refraction),
    xChannelSelector: 'R',
    yChannelSelector: 'G'
  }))
    lens.setAttribute(key, value)
  filter.append(blur, map, lens)
  defs.append(filter)
  svg.append(defs)
  document.body.append(svg)
  let frame = 0
  let lastSize = ''
  const opaque = matchMedia(
    '(prefers-reduced-transparency: reduce), (prefers-contrast: more), (forced-colors: active)'
  )
  const deform = (event: Event) => {
    if (opaque.matches || document.documentElement.dataset.material === 'opaque') return
    const compression = Math.max(-0.045, Math.min(0.1, Number((event as CustomEvent).detail) || 0))
    lens.setAttribute('scale', String(refraction * (1 + compression * 5)))
  }
  element.addEventListener('glass-deform', deform)
  function update() {
    frame = 0
    lens.setAttribute('scale', String(refraction))
    if (opaque.matches || document.documentElement.dataset.material === 'opaque') {
      map.removeAttribute('href')
      element.style.removeProperty('--glass-filter')
      lastSize = ''
      return
    }
    const { width, height } = element.getBoundingClientRect()
    if (width < 1 || height < 1) return
    const radius = parseFloat(getComputedStyle(element).borderTopLeftRadius) || 24
    const size = `${Math.round(width)}:${Math.round(height)}:${radius}`
    if (size === lastSize) return
    lastSize = size
    const field = lensMap(width, height, radius)
    const canvas = document.createElement('canvas')
    canvas.width = field.width
    canvas.height = field.height
    const context = canvas.getContext('2d')
    if (!context) return
    context.putImageData(new ImageData(field.pixels, field.width, field.height), 0, 0)
    map.setAttribute('href', canvas.toDataURL())
    element.style.setProperty('--glass-filter', `url("#${id}") saturate(1.45)`)
  }
  const observer = new ResizeObserver(() => {
    if (!frame) frame = requestAnimationFrame(update)
  })
  observer.observe(element)
  const preferenceChanged = () => {
    lastSize = ''
    if (!frame) frame = requestAnimationFrame(update)
  }
  opaque.addEventListener('change', preferenceChanged)
  const appearanceObserver = new MutationObserver(preferenceChanged)
  appearanceObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-material']
  })
  return () => {
    observer.disconnect()
    appearanceObserver.disconnect()
    opaque.removeEventListener('change', preferenceChanged)
    element.removeEventListener('glass-deform', deform)
    cancelAnimationFrame(frame)
    svg.remove()
    element.style.removeProperty('--glass-filter')
    element.removeAttribute('data-glass')
  }
}

const glass: ObjectDirective<HTMLElement, GlassFinish | undefined> = {
  mounted(element, binding) {
    dispose.set(element, opticalLayer(element, binding.value ?? 'regular'))
  },
  beforeUnmount(element) {
    dispose.get(element)?.()
    dispose.delete(element)
  }
}

export const glassMaterials = {
  install(app: App) {
    app.directive('glass', glass)
    const release = installFeedback()
    const releaseAppearance = installAppearance()
    app.onUnmount(release)
    app.onUnmount(releaseAppearance)
  }
}
