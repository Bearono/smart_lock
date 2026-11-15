// A rounded-rectangle lens normal field, not a screenshot of page content.
// R/G encode displacement; the flat center remains neutral and only the rim bends.
export function lensMap(width, height, radius) {
  const ratio = Math.min(1, 384 / Math.max(width, height, 1))
  const w = Math.max(1, Math.round(width * ratio))
  const h = Math.max(1, Math.round(height * ratio))
  const r = Math.max(1, Math.min(radius, width / 2, height / 2))
  const bevel = Math.max(1, Math.min(18, r * 0.85))
  const pixels = new Uint8ClampedArray(w * h * 4)
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const px = ((x + 0.5) / w - 0.5) * width
      const py = ((y + 0.5) / h - 0.5) * height
      const qx = Math.abs(px) - (width / 2 - r)
      const qy = Math.abs(py) - (height / 2 - r)
      const outer = Math.hypot(Math.max(qx, 0), Math.max(qy, 0))
      const distance = outer + Math.min(Math.max(qx, qy), 0) - r
      const strength = Math.pow(Math.max(0, 1 - Math.abs(distance) / bevel), 1.6)
      let nx = 0,
        ny = 0
      if (qx > 0 && qy > 0) {
        nx = (Math.sign(px) * qx) / outer
        ny = (Math.sign(py) * qy) / outer
      } else if (qx > qy) nx = Math.sign(px)
      else ny = Math.sign(py)
      const index = (y * w + x) * 4
      pixels[index] = 128 + 124 * nx * strength
      pixels[index + 1] = 128 + 124 * ny * strength
      pixels[index + 2] = 128
      pixels[index + 3] = 255
    }
  }
  return { width: w, height: h, pixels }
}
