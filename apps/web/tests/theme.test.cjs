const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

test('action, status and text tokens retain contrast on solid and worst-case glass backgrounds', () => {
  const css = fs.readFileSync(path.join(__dirname, '../src/shared/styles/tokens.css'), 'utf8')
  const tokens = Object.fromEntries(
    [...css.matchAll(/--([\w-]+):\s*(#[\da-f]{6,8});/gi)].map((match) => [match[1], match[2]])
  )
  function color(value, behind = [0, 0, 0]) {
    const alpha = value.length === 9 ? parseInt(value.slice(7), 16) / 255 : 1
    return [1, 3, 5].map(
      (offset, index) =>
        (alpha * parseInt(value.slice(offset, offset + 2), 16)) / 255 + (1 - alpha) * behind[index]
    )
  }
  function luminance(rgb) {
    return rgb
      .map((channel) => (channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4))
      .reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0)
  }
  function ratio(a, b) {
    const values = [luminance(a), luminance(b)].sort((x, y) => y - x)
    return (values[0] + 0.05) / (values[1] + 0.05)
  }
  const white = [1, 1, 1]
  assert.ok(ratio(white, color(tokens.primary)) >= 4.5, 'primary button text')
  assert.ok(ratio(white, color(tokens['primary-hover'])) >= 4.5, 'hovered primary button text')
  assert.ok(ratio(color(tokens.muted), white) >= 4.5, 'secondary text on content cards')
  const minimum = Number(css.match(/--material-min-opacity:\s*([\d.]+)/)[1])
  assert.ok(minimum >= 0 && minimum <= 1)
  for (let tint = 0; tint <= 100; tint += 5) {
    const alpha = minimum + (tint / 100) * (1 - minimum)
    assert.ok(
      ratio(color(tokens.ink), [alpha, alpha, alpha]) >= 4.5,
      `toolbar text over a completely black backdrop at tint ${tint}`
    )
  }
  assert.notEqual(
    tokens.primary,
    tokens.success,
    'actions and positive state must have separate roles'
  )
})
