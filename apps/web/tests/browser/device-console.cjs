/* Test the operator's shutter against fixtures only: never contact a real camera. */
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const { chromium } = require('playwright')

async function run() {
  const assets = path.resolve(__dirname, '../../../../deploy/device_console')
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {})
  })
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 960 } })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    let requests = 0
    let rejectCapture = false
    const state = {
      busy: false,
      phase: 'idle',
      error: '',
      history: [],
      expected: 'admin',
      csrf: 'fixture'
    }
    const sample = {
      id: 'a'.repeat(32),
      label: 'live_front',
      status: 'analyzing',
      snapshot: '/fixture.jpg',
      started_at: '2026-11-15T12:00:00Z',
      received_at: '2026-11-15T12:00:01Z'
    }
    await page.route('**/*', async (route) => {
      const request = route.request()
      const pathname = new URL(request.url()).pathname
      if (pathname === '/api/state') return route.fulfill({ json: state })
      if (pathname === '/api/capture') {
        requests++
        assert.equal(request.method(), 'POST')
        assert.equal(request.headers()['x-test-csrf'], 'fixture')
        assert.deepEqual(request.postDataJSON(), { label: 'live_front' })
        if (rejectCapture) return route.fulfill({ status: 503, json: { error: 'fixture' } })
        state.busy = true
        state.phase = 'analyzing'
        state.history = [sample]
        return route.fulfill({ status: 202, json: { accepted: true } })
      }
      if (pathname.startsWith('/image/'))
        return route.fulfill({
          contentType: 'image/svg+xml',
          body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"><rect width="640" height="480" fill="#314254"/><text x="210" y="245" fill="white" font-size="26">Camera test fixture</text></svg>'
        })
      const files = {
        '/': ['index.html', 'text/html'],
        '/app.js': ['app.js', 'text/javascript'],
        '/style.css': ['style.css', 'text/css']
      }
      assert.ok(files[pathname], 'Unexpected request: ' + pathname)
      return route.fulfill({
        body: await fs.readFile(path.join(assets, files[pathname][0])),
        contentType: files[pathname][1]
      })
    })
    await page.clock.install()
    await page.goto('http://camera.test/')
    await page.waitForFunction(() => !document.getElementById('shoot').disabled)
    await page.clock.fastForward(5000)
    assert.equal(requests, 0, 'Loading and polling must never take photos')
    await page.locator('#shoot').click()
    assert.equal(await page.locator('#countdown').isVisible(), true)
    await page.locator('#cancel').click()
    await page.clock.fastForward(5000)
    assert.equal(requests, 0, 'Cancelled countdown must never take photos')
    assert.match(await page.locator('#status').textContent(), /已取消/)
    await page.locator('#shoot').click()
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { value: true, configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))
      Object.defineProperty(document, 'hidden', { value: false, configurable: true })
    })
    await page.clock.fastForward(5000)
    assert.equal(requests, 0, 'Leaving the page must cancel countdown')
    await page.locator('#delay').selectOption('0')
    await page.locator('#shoot').click()
    await page.waitForFunction(() =>
      document.getElementById('status').textContent.includes('照片已拍好')
    )
    assert.equal(requests, 1)
    assert.equal(await page.locator('#shoot').isDisabled(), true)
    assert.equal(await page.locator('#photo').isVisible(), true)
    state.busy = false
    state.phase = 'complete'
    sample.status = 'complete'
    sample.analysis = { face_count: 1, identity: 'admin', similarity: 0.97, pad_score: 0.91 }
    sample.sample_passed = true
    await page.clock.fastForward(1600)
    await page.waitForFunction(() =>
      document.getElementById('results').textContent.includes('0.910')
    )
    await fs.mkdir(path.resolve(__dirname, '../../test-artifacts'), { recursive: true })
    await page.screenshot({
      path: path.resolve(__dirname, '../../test-artifacts/device-console-desktop.png'),
      fullPage: true
    })
    await page.setViewportSize({ width: 390, height: 844 })
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true
    )
    await page.screenshot({
      path: path.resolve(__dirname, '../../test-artifacts/device-console-mobile.png'),
      fullPage: true
    })
    rejectCapture = true
    await page.locator('#shoot').click()
    await page.waitForFunction(() =>
      document.getElementById('status').textContent.includes('请求未确认')
    )
    await page.clock.fastForward(2000)
    assert.match(await page.locator('#status').textContent(), /请求未确认/)
    assert.equal(requests, 2, 'Uncertain requests must not auto-retry')
    assert.deepEqual(errors, [])
    console.log(
      'Camera console: explicit capture, cancellation, early photo, busy state, errors and mobile layout passed (fixtures only).'
    )
  } finally {
    await browser.close()
  }
}
run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
