const { test } = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const { pathToFileURL } = require('node:url')
const root = path.join(__dirname, '../src/shared/material')

test('spring rebounds and settles across 30, 60 and 120 Hz without runaway on a frame stall', async () => {
  const { advanceSpring, springSettled } = await import(pathToFileURL(path.join(root, 'spring.js')))
  for (const rate of [30, 60, 120]) {
    let state = { position: 0.945, velocity: 0.9 }
    let peak = 1
    for (let frame = 0; frame < rate * 2; frame++) {
      state = advanceSpring(state, 1, frame === 3 ? 0.6 : 1 / rate)
      peak = Math.max(peak, state.position)
      assert.ok(Number.isFinite(state.position) && state.position > 0.9 && state.position < 1.05)
    }
    assert.ok(peak > 1.001, 'release should overshoot, rather than linear scale-back')
    assert.ok(springSettled(state, 1), `${rate} Hz should settle`)
  }
})

test('lens normals are neutral centrally, mirrored at the rim, bounded in memory and opaque', async () => {
  const { lensMap } = await import(pathToFileURL(path.join(root, 'optics.js')))
  for (const [width, height, radius] of [
    [220, 700, 28],
    [900, 64, 24],
    [390, 72, 28],
    [1, 1, 0]
  ]) {
    const field = lensMap(width, height, radius)
    assert.ok(field.width <= 384 && field.height <= 384)
    assert.equal(field.pixels.length, field.width * field.height * 4)
    assert.ok(field.pixels.every((value, index) => index % 4 !== 3 || value === 255))
    if (width > 100) {
      const center = (Math.floor(field.height / 2) * field.width + Math.floor(field.width / 2)) * 4
      assert.equal(field.pixels[center], 128)
      assert.equal(field.pixels[center + 1], 128)
      const left = Math.floor(field.height / 2) * field.width * 4
      const right = left + (field.width - 1) * 4
      assert.ok(field.pixels[left] < 128 && field.pixels[right] > 128)
      assert.ok(Math.abs(field.pixels[left] + field.pixels[right] - 256) <= 1)
    }
  }
})
