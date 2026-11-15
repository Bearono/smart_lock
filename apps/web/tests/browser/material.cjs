/* Isolated visual/interaction acceptance. No sign-in or business data writes. */
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const { chromium } = require('playwright')
const base = process.env.FRONTEND_URL || 'http://127.0.0.1:5173'
async function run() {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {})
  })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.addInitScript(() => {
      window.__materialFrames = 0
      window.__nativeFrame = window.requestAnimationFrame.bind(window)
      window.requestAnimationFrame = (callback) => {
        window.__materialFrames++
        return window.__nativeFrame(callback)
      }
    })
    await page.goto(base)
    const button = page.getByRole('button', { name: '继续验证', exact: true })
    await button.waitFor()
    await page.waitForFunction(() =>
      document
        .querySelector('[data-glass]')
        ?.style.getPropertyValue('--glass-filter')
        .includes('url(')
    )
    const optical = await page
      .locator('[data-glass]')
      .first()
      .evaluate((element) => ({
        filter: getComputedStyle(element).backdropFilter,
        image: document.querySelector('feImage')?.getAttribute('href')
      }))
    assert.match(optical.filter, /url\(/)
    assert.ok(optical.image.startsWith('data:image/png;'))
    const loginLenses = await page.locator('filter[id^="smartlock-lens-"]').count()
    const refraction = () =>
      button.evaluate((element) => {
        const id = element.style.getPropertyValue('--glass-filter').match(/#([^\"]+)/)[1]
        return Number(
          document.getElementById(id).querySelector('feDisplacementMap').getAttribute('scale')
        )
      })
    const restingRefraction = await refraction()
    const box = await button.boundingBox()
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.down()
    await page.waitForFunction(
      () =>
        Number(
          document
            .querySelector('button[type="submit"], .form-section .button')
            ?.style.getPropertyValue('--press-scale')
        ) < 0.98
    )
    assert.ok(
      (await refraction()) > restingRefraction,
      'press changes the live background refraction'
    )
    assert.ok(
      await button.evaluate(
        (element) => Number(element.style.getPropertyValue('--press-width')) > 1
      ),
      'compression expands the control horizontally'
    )
    const samples = page.evaluate(
      () =>
        new Promise((resolve) => {
          const values = []
          function collect() {
            values.push(
              Number(
                document
                  .querySelector('.form-section .button')
                  ?.style.getPropertyValue('--press-scale')
              ) || 1
            )
            if (values.length < 90) window.__nativeFrame(collect)
            else resolve(values)
          }
          window.__nativeFrame(collect)
        })
    )
    await page.mouse.up()
    const values = await samples
    assert.ok(Math.max(...values) > 1.001, 'real browser release overshoots')
    assert.ok(Math.abs(values.at(-1) - 1) < 0.001, 'spring returns to rest')
    await page.waitForFunction(
      () =>
        !document.querySelector('.form-section .button')?.style.getPropertyValue('--press-scale')
    )
    assert.equal(await refraction(), restingRefraction, 'refraction returns to rest')
    await page
      .evaluate(
        () =>
          new Promise((resolve) => {
            const before = window.__materialFrames
            let frames = 0
            function wait() {
              if (++frames < 30) window.__nativeFrame(wait)
              else resolve(before === window.__materialFrames)
            }
            window.__nativeFrame(wait)
          })
      )
      .then((idle) => assert.ok(idle, 'no permanent idle animation loop'))
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.mouse.down()
    assert.equal(await button.evaluate((element) => getComputedStyle(element).transform), 'none')
    await page.mouse.up()
    await page.emulateMedia({ forcedColors: 'active' })
    assert.equal(
      await page
        .locator('[data-glass]')
        .first()
        .evaluate((element) => getComputedStyle(element).backdropFilter),
      'none'
    )
    await page.emulateMedia({ forcedColors: 'none', reducedMotion: 'no-preference' })
    await page.emulateMedia({ contrast: 'more' })
    assert.equal(
      await page
        .locator('[data-glass]')
        .first()
        .evaluate((element) => getComputedStyle(element).backdropFilter),
      'none'
    )
    await page.waitForFunction(() => !document.querySelector('feImage')?.hasAttribute('href'))
    await page.emulateMedia({ contrast: 'no-preference' })
    await page.waitForFunction(() =>
      document.querySelector('feImage')?.getAttribute('href')?.startsWith('data:image/png;')
    )
    for (let index = 0; index < 3; index++) {
      await page.goto(base + '/guest')
      assert.equal(await page.locator('filter[id^="smartlock-lens-"]').count(), 0)
      await page.goto(base)
      await button.waitFor()
      assert.equal(await page.locator('filter[id^="smartlock-lens-"]').count(), loginLenses)
    }
    const register = page.getByRole('button', { name: '创建账户', exact: true })
    const edge = await register.boundingBox()
    await page.mouse.move(edge.x + 2, edge.y + edge.height / 2)
    await page.mouse.down()
    await page.waitForFunction(
      () =>
        Number(
          document.querySelector('.auth-links button')?.style.getPropertyValue('--press-scale')
        ) < 0.97
    )
    await page.mouse.up()
    await page.getByRole('heading', { name: '创建账户', exact: true }).waitFor()
    await page.goto(base)
    await button.focus()
    await page.keyboard.down('Enter')
    await page.waitForFunction(
      () =>
        Number(
          document.querySelector('.form-section .button')?.style.getPropertyValue('--press-scale')
        ) < 0.99
    )
    await page.keyboard.up('Enter')
    await page.waitForFunction(
      () =>
        !document.querySelector('.form-section .button')?.style.getPropertyValue('--press-scale')
    )
    await page.screenshot({
      path: path.resolve(__dirname, '../../test-artifacts/glass-login-desktop.png'),
      fullPage: true
    })
    assert.deepEqual(errors, [])
    const report = {
      passed: true,
      checks: [
        'live SVG backdrop lens',
        'pressed scale',
        'horizontal deformation and dynamic refraction',
        'spring overshoot and settling',
        'no idle animation loop',
        'reduced motion',
        'forced colors',
        'increased contrast disables and restores optical resources',
        'route resource disposal',
        'stable edge hit target',
        'keyboard press and release'
      ],
      minScale: Math.min(...values),
      maxScale: Math.max(...values)
    }
    const output = process.env.MATERIAL_REPORT
    if (output) await fs.writeFile(output, JSON.stringify(report, null, 2))
    console.log(JSON.stringify(report))
  } finally {
    await browser.close()
  }
}
run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
