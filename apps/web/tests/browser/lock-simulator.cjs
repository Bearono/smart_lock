/* Exercise the read-only simulator panel against isolated HTTP fixtures. */
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const http = require('node:http')
const path = require('node:path')
const { chromium } = require('playwright')

const token = 'fixture-viewer-token'
const assets = path.resolve(__dirname, '../../../lock_sim/static')
const artifacts = path.resolve(__dirname, '../../test-artifacts')
const fixedTime = Date.parse('2026-11-16T10:30:00Z') / 1000

function command(index, target, reported = target) {
  return {
    id: index.toString(16).padStart(32, '0'),
    target_status: target,
    reported_status: reported,
    status: reported === target ? 'executed' : 'failed',
    executed_at: fixedTime - (8 - index) * 30
  }
}

function snapshot(reported = 'LOCKED', fault = 'normal', commands = []) {
  return {
    execution_mode: 'SIMULATED',
    reported_status: reported,
    fault,
    command_count: commands.length,
    architecture: 'aarch64',
    observed_at: fixedTime,
    commands
  }
}

async function fixture() {
  const files = new Map(
    await Promise.all(
      [
        ['/panel', 'panel.html', 'text/html; charset=utf-8'],
        ['/static/panel.css', 'panel.css', 'text/css; charset=utf-8'],
        ['/static/panel.js', 'panel.js', 'text/javascript; charset=utf-8'],
        ['/static/favicon.svg', 'favicon.svg', 'image/svg+xml']
      ].map(async ([route, file, type]) => [
        route,
        [await fs.readFile(path.join(assets, file)), type]
      ])
    )
  )
  const fixtureState = { value: snapshot(), status: 200, reads: 0, requests: [] }
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, 'http://localhost').pathname
    fixtureState.requests.push({ method: request.method, pathname })
    response.setHeader('Cache-Control', 'no-store')
    response.setHeader(
      'Content-Security-Policy',
      "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )
    response.setHeader('X-Content-Type-Options', 'nosniff')
    response.setHeader('Referrer-Policy', 'no-referrer')
    if (pathname === '/panel/state') {
      fixtureState.reads++
      const authorized = request.headers.authorization === `Bearer ${token}`
      response.writeHead(authorized ? fixtureState.status : 401, {
        'Content-Type': 'application/json'
      })
      response.end(JSON.stringify(authorized ? fixtureState.value : { msg: 'Unauthorized' }))
      return
    }
    const file = files.get(pathname)
    if (file && request.method === 'GET') {
      response.writeHead(200, { 'Content-Type': file[1] })
      response.end(file[0])
      return
    }
    response.writeHead(pathname === '/favicon.ico' ? 204 : 404)
    response.end()
  })
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  return {
    state: fixtureState,
    url: `http://127.0.0.1:${server.address().port}/panel`,
    close: () => new Promise((resolve) => server.close(resolve))
  }
}

async function waitState(page, state, connection = 'online') {
  await page.waitForFunction(
    ({ state, connection }) =>
      document.body.dataset.state === state && document.body.dataset.connection === connection,
    { state, connection }
  )
}

async function capture(page, label) {
  await page
    .locator('#bolt')
    .evaluate((element) =>
      Promise.all(element.getAnimations().map((animation) => animation.finished.catch(() => {})))
    )
  await page.screenshot({
    path: path.join(artifacts, `lock-simulator-${label}.png`),
    fullPage: true
  })
}

async function assertFits(page) {
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    true,
    'The panel must fit the viewport without horizontal scrolling'
  )
  for (const selector of ['#status-title', '#connection-label', '#latest-result']) {
    const box = await page.locator(selector).boundingBox()
    assert.ok(box && box.width > 0 && box.height > 0, `${selector} must remain visible`)
    assert.ok(box.x >= 0 && box.x + box.width <= page.viewportSize().width + 1)
  }
  if (page.viewportSize().width <= 480) {
    const door = await page.locator('.door-card').boundingBox()
    for (const selector of ['.latest-card', '.history-card']) {
      const card = await page.locator(selector).boundingBox()
      assert.ok(
        Math.abs(card.x - door.x) < 1 && Math.abs(card.width - door.width) < 1,
        `${selector} must align with the door card on phones`
      )
    }
  }
}

async function run() {
  await fs.mkdir(artifacts, { recursive: true })
  const host = await fixture()
  let browser
  const errors = []
  try {
    browser = await chromium.launch({
      headless: true,
      ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {})
    })
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      locale: 'zh-CN',
      timezoneId: 'Asia/Shanghai'
    })
    const page = await context.newPage()
    await page.clock.setFixedTime(new Date(fixedTime * 1000))
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('console', (message) => {
      if (message.text().startsWith('CSP violation:')) errors.push(message.text())
    })
    await page.addInitScript(() => {
      document.addEventListener('securitypolicyviolation', (event) =>
        console.error(`CSP violation: ${event.violatedDirective}`)
      )
    })

    await page.goto(host.url)
    await page.locator('#authorization-help').waitFor({ state: 'visible' })
    assert.equal(host.state.reads, 0, 'A missing viewer credential must not start polling')
    await capture(page, 'authorization')

    await page.goto(`${host.url}#token=${token}`)
    await waitState(page, 'LOCKED')
    assert.equal(
      new URL(page.url()).hash,
      '',
      'The bootstrap credential must leave browser history'
    )
    assert.equal(
      await page.evaluate(() => sessionStorage.getItem('smartlock.simulator.viewer')),
      token
    )
    assert.equal(await page.locator('#history .history-item').count(), 0)
    assert.match(await page.locator('#status-title').textContent(), /已上锁/)
    await capture(page, 'locked-empty')
    await page.reload()
    await waitState(page, 'LOCKED')
    assert.equal(
      await page.locator('#authorization-help').isVisible(),
      false,
      'Reloading the panel must retain the tab-scoped viewer credential'
    )

    host.state.value = snapshot('UNLOCKED', 'normal', [command(1, 'UNLOCKED')])
    await waitState(page, 'UNLOCKED')
    assert.match(await page.locator('#status-title').textContent(), /已解锁/)
    assert.equal(await page.locator('#history .history-item').count(), 1)
    await capture(page, 'unlocked')
    const openedBolt = await page
      .locator('#bolt')
      .evaluate((element) => getComputedStyle(element).transform)

    host.state.value = snapshot('LOCKED', 'normal', [command(2, 'LOCKED'), command(1, 'UNLOCKED')])
    await waitState(page, 'LOCKED')
    await page.waitForFunction(
      (opened) => getComputedStyle(document.getElementById('bolt')).transform !== opened,
      openedBolt
    )
    assert.equal(await page.locator('#history .history-item').count(), 2)
    const readsBeforeReplay = host.state.reads
    await page.waitForFunction(
      () => document.querySelectorAll('#history .history-item').length === 2
    )
    await page.waitForTimeout(1500)
    assert.ok(host.state.reads > readsBeforeReplay, 'The displayed state must continue polling')
    assert.equal(
      await page.locator('#history .history-item').count(),
      2,
      'Polling must not duplicate history'
    )

    host.state.value = snapshot('LOCKED', 'jammed', [command(3, 'UNLOCKED', 'LOCKED')])
    await page.waitForFunction(() =>
      document.querySelector('#history .history-item')?.dataset.commandId.endsWith('3')
    )
    await waitState(page, 'LOCKED')
    assert.doesNotMatch(await page.locator('#latest-result').textContent(), /成功/)
    await capture(page, 'jammed')

    host.state.value = snapshot('UNKNOWN', 'feedback_lost', [command(4, 'UNLOCKED', 'UNKNOWN')])
    await waitState(page, 'UNKNOWN')
    assert.match(await page.locator('#status-title').textContent(), /状态未知/)
    await capture(page, 'unknown')

    host.state.value = snapshot('UNLOCKED', 'normal', [command(5, 'UNLOCKED')])
    await waitState(page, 'UNLOCKED')
    host.state.status = 503
    await page.waitForFunction(() => document.body.dataset.connection === 'offline')
    assert.match(await page.locator('#status-title').textContent(), /连接中断/)
    await capture(page, 'offline')
    host.state.status = 200
    host.state.value = snapshot('LOCKED', 'normal', [command(6, 'LOCKED')])
    await waitState(page, 'LOCKED')
    await capture(page, 'recovered')

    host.state.value = { ...snapshot('UNLOCKED'), execution_mode: 'PHYSICAL' }
    await page.waitForFunction(() => document.body.dataset.connection === 'offline')
    assert.doesNotMatch(await page.locator('#status-title').textContent(), /^已解锁$/)
    host.state.value = snapshot('LOCKED')
    await waitState(page, 'LOCKED')

    const contradictory = { ...command(10, 'UNLOCKED', 'LOCKED'), status: 'executed' }
    host.state.value = snapshot('LOCKED', 'normal', [contradictory])
    await page.waitForFunction(() => document.body.dataset.connection === 'offline')
    assert.equal(
      await page.locator('#history .history-item').count(),
      0,
      'Contradictory execution success must not enter the displayed history'
    )
    host.state.value = snapshot('LOCKED')
    await waitState(page, 'LOCKED')

    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { value: true, configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    const hiddenReads = host.state.reads
    await page.waitForTimeout(1500)
    assert.equal(host.state.reads, hiddenReads, 'A hidden panel must pause polling')
    host.state.value = snapshot('UNLOCKED', 'normal', [command(7, 'UNLOCKED')])
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { value: false, configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await waitState(page, 'UNLOCKED')

    host.state.value = snapshot(
      'LOCKED',
      'normal',
      Array.from({ length: 8 }, (_, index) => {
        const item = command(8 - index, index % 2 ? 'UNLOCKED' : 'LOCKED')
        if (index === 7) item.executed_at = null
        return item
      })
    )
    await page.waitForFunction(
      () => document.querySelectorAll('#history .history-item').length === 8
    )
    assert.doesNotMatch(await page.locator('#history').textContent(), /Invalid Date|1970/)
    for (const [width, height] of [
      [1920, 1080],
      [1280, 900],
      [768, 1024],
      [390, 844],
      [320, 740]
    ]) {
      await page.setViewportSize({ width, height })
      await assertFits(page)
      await capture(page, `responsive-${width}`)
    }

    const recentSnapshot = host.state.value
    host.state.value = {
      ...recentSnapshot,
      commands: recentSnapshot.commands.map((entry) => ({
        ...entry,
        executed_at: entry.executed_at === null ? null : entry.executed_at - 86400
      }))
    }
    await page.waitForFunction(() =>
      document.getElementById('latest-time').textContent.includes('11/15')
    )
    await assertFits(page)
    const history = await page.locator('#history').boundingBox()
    for (const time of await page.locator('#history .history-time').all()) {
      const box = await time.boundingBox()
      assert.ok(
        box.x >= history.x && box.x + box.width <= history.x + history.width + 1,
        'Cross-day timestamps must fit the phone history column'
      )
    }
    await capture(page, 'cross-day-320')
    host.state.value = recentSnapshot
    await page.waitForFunction(
      () => !document.getElementById('latest-time').textContent.includes('/')
    )

    await page.setViewportSize({ width: 1920, height: 1080 })
    if (await page.evaluate(() => document.fullscreenEnabled)) {
      await page.locator('#fullscreen-toggle').click()
      await page.waitForFunction(() => Boolean(document.fullscreenElement))
      assert.match(await page.locator('#fullscreen-toggle').getAttribute('aria-label'), /退出全屏/)
      await capture(page, 'fullscreen')
      await page.locator('#fullscreen-toggle').click()
      await page.waitForFunction(() => !document.fullscreenElement)
      assert.match(await page.locator('#fullscreen-toggle').getAttribute('aria-label'), /全屏/)
    }

    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.setViewportSize({ width: 1280, height: 900 })
    host.state.value = snapshot('UNLOCKED', 'normal', [command(9, 'UNLOCKED')])
    await waitState(page, 'UNLOCKED')
    const durations = await page.locator('#bolt').evaluate((element) => {
      const style = getComputedStyle(element)
      return [style.transitionDuration, style.animationDuration]
    })
    assert.ok(
      durations.every((value) =>
        value.split(',').every((duration) => parseFloat(duration) <= 0.01)
      ),
      'Reduced motion must disable lengthy bolt animations'
    )

    host.state.status = 401
    await page.waitForFunction(() => document.body.dataset.connection === 'unauthorized')
    assert.equal(
      await page.evaluate(() => sessionStorage.getItem('smartlock.simulator.viewer')),
      null
    )
    await page.locator('#authorization-help').waitFor({ state: 'visible' })
    const rejectedReads = host.state.reads
    await page.waitForTimeout(1500)
    assert.equal(host.state.reads, rejectedReads, 'Rejected credentials must stop polling')
    host.state.status = 200
    await page.goto(`${host.url}#token=${token}`)
    await waitState(page, 'UNLOCKED')

    assert.ok(
      host.state.requests.every(({ method }) => method === 'GET'),
      'The simulator panel must never send an actuation or fault mutation'
    )
    assert.ok(
      host.state.requests.every(
        ({ pathname }) => !['/commands', '/fault', '/state'].includes(pathname)
      )
    )
    assert.deepEqual(errors, [])
    console.log(
      'Lock simulator panel: observed transitions, history, auth, offline recovery, reduced motion and five viewport sizes passed (isolated fixtures).'
    )
  } finally {
    if (browser) await browser.close()
    await host.close()
  }
}

run().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
