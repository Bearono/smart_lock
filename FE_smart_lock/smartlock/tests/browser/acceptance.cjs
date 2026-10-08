/* Deterministic browser acceptance. Fixtures exist only in this test process. */
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const { chromium } = require('playwright')
const base = process.env.FRONTEND_URL || 'http://127.0.0.1:5173'
const artifacts = path.resolve(__dirname, '../../test-artifacts')
const devices = [
  {
    device_id: 'qa_front',
    is_online: true,
    reported_status: 'LOCKED',
    status: 'UNLOCKED',
    battery: 86,
    camera_status: 'ONLINE',
    last_update: '2026-10-08 14:30:00'
  },
  {
    device_id: 'qa_back',
    is_online: false,
    reported_status: 'UNKNOWN',
    battery: null,
    camera_status: 'UNKNOWN',
    last_update: null
  }
]
const users = [
  {
    id: 1,
    username: 'qa_operator',
    role: 'admin',
    status: 'approved',
    created_at: '2026-10-08 09:00:00'
  },
  {
    id: 2,
    username: '待审批用户',
    role: 'user',
    status: 'pending',
    created_at: '2026-10-08 10:00:00'
  }
]
const logs = [
  { id: 1, username: 'qa_operator', action: 'TOKEN_UNLOCK', timestamp: '2026-10-08 14:30:00' }
]
const faceLogs = [
  {
    id: 1,
    request_id: 'request-1',
    device_id: 'qa_front',
    expected_username: 'qa_operator',
    face_user_id: 'qa_operator',
    passed: true,
    similarity_score: 0.96,
    timestamp: '2026-10-08 14:30:00',
    snapshot: null
  }
]
const calls = { verify: 0, consume: 0, face: 0, lock: 0 }
let lostConsumption = false,
  rejectGrant = false,
  deviceFailure = false,
  commandConfirmed = false
let guestPasses = [],
  activeGrants = ['qa_front', 'registered_but_not_reported']
let browser
let snapshotFixtures = false,
  receiptUnauthorized = false,
  emptyDevices = false

async function fixture(page) {
  await page.route('**/api/**', async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      endpoint = url.pathname
    if (!endpoint.startsWith('/api/')) return route.continue()
    const body = request.postDataJSON() || {}
    const respond = (data, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) })
    if (endpoint === '/api/login/pre')
      return respond({ pre_token: 'qa-pre', totp_bound: true, role: 'admin' })
    if (endpoint === '/api/login/mfa/verify')
      return respond({ access_token: 'qa-fixture', role: 'admin' })
    if (endpoint === '/api/device/status')
      return deviceFailure
        ? respond({ msg: '设备状态获取失败' }, 503)
        : respond(emptyDevices ? [] : devices)
    if (endpoint === '/api/admin/security/evidence')
      return respond({
        observed_at: '2026-10-08T00:00:00Z',
        verification: null,
        protocol: {
          version: 'SL-SEC-v3',
          handshake: 'SPAKE2',
          envelope: 'AES-256-GCM',
          legacy_upload_enabled: false
        },
        controls: [{ name: '设备权限', detail: '管理员授权与认证绑定' }],
        storage: { sessions: 1, receipts: 2, commands: 3 },
        limitations: ['隔离测试数据，未验证实机。']
      })
    if (/\/api\/admin\/devices\/[^/]+\/name$/.test(endpoint)) {
      const target = devices.find((item) => item.device_id === endpoint.split('/')[4])
      target.display_name = body.display_name
      return respond(target)
    }
    if (endpoint === '/api/video/latest')
      return respond({
        snapshot: snapshotFixtures
          ? `/api/media/${(url.searchParams.get('device_id') === 'qa_back' ? 'b' : 'a').repeat(32)}.jpg`
          : null
      })
    if (endpoint.startsWith('/api/media/')) {
      const back = endpoint.includes('bbbb')
      if (back) await new Promise((resolve) => setTimeout(resolve, 350))
      return route.fulfill({
        contentType: 'image/svg+xml',
        body: `<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="${back ? '#0000ff' : '#ff0000'}"/></svg>`
      })
    }
    if (endpoint === '/api/mfa/status')
      return respond({
        totp_bound: true,
        devices: devices.map((item, index) => ({
          credential_id: index + 1,
          device_id: item.device_id,
          is_active: true,
          created_at: '2026-10-08 09:00:00'
        }))
      })
    if (endpoint === '/api/mfa/open-door/request') {
      calls.face++
      return respond({
        request_id: 'request-1',
        requires_totp: true,
        device_dispatch: { status: 'processed', backend_reply: { msg: 'Face verified' } }
      })
    }
    if (endpoint === '/api/mfa/open-door/confirm')
      return body.totp_code === '000000'
        ? respond({ msg: 'Invalid TOTP code' }, 401)
        : respond({ unlock_token: 'qa-token', device_id: 'qa_front' })
    if (endpoint === '/api/lock/control') {
      calls.lock++
      return respond({ command_id: 'lock-1', command_accepted: true, hardware_confirmed: false })
    }
    if (endpoint === '/api/lock/unlock-token/verify') {
      calls.consume++
      if (lostConsumption) {
        lostConsumption = false
        return route.abort('failed')
      }
      return respond({ command_id: 'command-1', command_accepted: true, hardware_confirmed: false })
    }
    if (receiptUnauthorized && endpoint === '/api/lock/command-status')
      return respond({ msg: 'Capability expired' }, 401)
    if (endpoint === '/api/lock/command-status' || endpoint.startsWith('/api/lock/commands/'))
      return respond({
        id: endpoint.includes('lock-1') ? 'lock-1' : 'command-1',
        status: commandConfirmed ? 'executed' : 'pending',
        hardware_confirmed: commandConfirmed
      })
    if (endpoint === '/api/lock/history')
      return respond({ data: logs, total: 1, pages: 1, current_page: 1 })
    if (endpoint === '/api/face/logs')
      return respond({
        data: url.searchParams.get('passed') === 'false' ? [] : faceLogs,
        total: 1,
        pages: 1,
        current_page: 1
      })
    if (endpoint === '/api/mfa/guest/verify') {
      calls.verify++
      return respond({ unlock_token: 'guest-token', device_id: 'qa_front' })
    }
    if (endpoint === '/api/mfa/guest/list') return respond(guestPasses)
    if (endpoint === '/api/mfa/guest/create') {
      guestPasses = [
        {
          id: 1,
          guest_name: body.guest_name,
          device_id: body.device_id,
          valid_until: '2026-10-09 14:30:00',
          max_uses: body.max_uses,
          used_count: 0,
          is_active: true
        }
      ]
      return respond({ pass_code: 'one-time-qa-code', valid_until: '2026-10-09 14:30:00' })
    }
    if (endpoint.startsWith('/api/mfa/guest/revoke/')) {
      guestPasses[0].is_active = false
      return respond({ msg: 'revoked' })
    }
    if (endpoint === '/api/alarms')
      return respond([
        {
          id: 1,
          time: '2026-10-08 14:30:00',
          type: '认证异常',
          message: '测试事件：请核查认证失败记录。',
          status: 'pending',
          email_status: 'disabled'
        }
      ])
    if (endpoint.startsWith('/api/alarms/')) return respond({ msg: 'updated' })
    if (endpoint === '/api/admin/users')
      return respond(
        users.filter(
          (user) =>
            !url.searchParams.get('status') || user.status === url.searchParams.get('status')
        )
      )
    if (/\/api\/admin\/users\/\d+\/devices$/.test(endpoint))
      return respond({ device_ids: activeGrants })
    if (/\/api\/admin\/users\/\d+\/devices\//.test(endpoint)) {
      if (rejectGrant) return respond({ msg: 'Device disabled' }, 400)
      const id = decodeURIComponent(endpoint.split('/').pop())
      activeGrants = body.granted
        ? [...new Set([...activeGrants, id])]
        : activeGrants.filter((item) => item !== id)
      return respond({ msg: 'updated' })
    }
    if (/\/api\/admin\/users\/\d+\/(approve|reject)$/.test(endpoint))
      return respond({ msg: 'updated' })
    if (endpoint === '/api/mfa/admin/device/unlock') return respond({ msg: 'updated' })
    if (endpoint === '/api/account/password') return respond({ msg: 'updated' })
    throw new Error(`Unexpected fixture endpoint: ${request.method()} ${endpoint}`)
  })
}
async function noOverflow(page, label) {
  const overflow = await page.evaluate(() =>
    [...document.querySelectorAll('body *')]
      .filter((element) => element.getBoundingClientRect().right > innerWidth + 1)
      .slice(0, 8)
      .map((element) => ({
        tag: element.tagName,
        class: element.className,
        text: element.textContent.slice(0, 40)
      }))
  )
  if (overflow.length) console.log(label, overflow)
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
    true,
    `${label} has horizontal overflow`
  )
}
async function run() {
  await fs.mkdir(artifacts, { recursive: true })
  browser = await chromium.launch({
    headless: true,
    ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {})
  })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await context.newPage(),
    errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'warning' && message.text().includes('[Vue warn]'))
      errors.push(message.text())
  })
  await fixture(page)
  await page.goto(base)
  await page.getByLabel('用户名', { exact: true }).fill('qa_operator')
  await page.getByLabel('密码', { exact: true }).fill('test-fixture-password')
  await page.getByRole('button', { name: '继续验证' }).click()
  await page.getByLabel('身份验证器验证码', { exact: true }).fill('123456')
  await page.getByRole('button', { name: '确认登录' }).click()
  await page.getByRole('button', { name: '验证并开门' }).waitFor()
  assert.equal(await page.locator('.lock-hero strong').textContent(), '已锁')
  await noOverflow(page, 'desktop door')
  await page.screenshot({ path: path.join(artifacts, 'doors-desktop.png'), fullPage: true })
  snapshotFixtures = true
  await page.getByRole('button', { name: '刷新快照', exact: true }).click()
  await page.locator('.snapshot-button img').waitFor()
  const slowImage = page.waitForRequest((request) => request.url().includes('/api/media/bbbb'))
  await page.locator('#device-select').selectOption('qa_back')
  await slowImage
  const slowResponse = page.waitForResponse((response) =>
    response.url().includes('/api/media/bbbb')
  )
  await page.locator('#device-select').selectOption('qa_front')
  await slowResponse
  await page.waitForFunction(() => {
    const image = document.querySelector('.snapshot-button img')
    if (!image || !image.complete) return false
    const canvas = document.createElement('canvas'),
      context = canvas.getContext('2d')
    canvas.width = canvas.height = 1
    context.drawImage(image, 0, 0, 1, 1)
    const pixel = context.getImageData(0, 0, 1, 1).data
    return pixel[0] === 255 && pixel[2] === 0
  })
  snapshotFixtures = false
  await page.getByRole('button', { name: '刷新快照', exact: true }).click()

  await page.getByRole('button', { name: '验证并开门' }).click()
  await page.getByLabel('身份验证器验证码', { exact: true }).fill('123456')
  lostConsumption = true
  await page.getByRole('button', { name: '确认并提交开门' }).click()
  await page.getByText('命令已提交，正在等待设备执行确认', { exact: true }).waitFor()
  assert.equal(calls.consume, 1)
  assert.equal(await page.locator('#device-select').isDisabled(), true)
  await page.getByRole('link', { name: '动态', exact: true }).click()
  commandConfirmed = true
  await page.getByText('设备已确认本次命令执行', { exact: true }).waitFor()
  await page.getByRole('tab', { name: '人脸验证', exact: true }).click()
  await page.getByRole('button', { name: '查看详情' }).click()
  await page.getByRole('dialog').getByText('0.96', { exact: true }).waitFor()
  await page.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('link', { name: '我的家', exact: true }).click()
  assert.equal(
    await page.locator('.lock-hero strong').textContent(),
    '已锁',
    'receipt must not replace reported state'
  )
  await page.locator('#device-select').selectOption('qa_back')
  assert.equal(await page.locator('.lock-hero strong').textContent(), '未知')
  await page.getByRole('button', { name: '上锁', exact: true }).click()
  await page.getByText('命令 ID：lock-1', { exact: true }).waitFor()
  assert.equal(calls.lock, 1, 'unknown sensor still allows explicit lock')
  await page.getByText('设备已确认本次命令执行', { exact: true }).waitFor()
  await page.locator('#device-select').selectOption('qa_front')
  await page.getByRole('button', { name: '验证并开门' }).click()
  await page.getByLabel('身份验证器验证码', { exact: true }).fill('000000')
  await page.getByRole('button', { name: '确认并提交开门' }).click()
  await page.getByText('验证码不正确，请重新开始验证', { exact: true }).waitFor()
  await page.getByRole('button', { name: '返回家门守护' }).click()
  deviceFailure = true
  await page.getByRole('button', { name: '刷新状态', exact: true }).click()
  await page.getByText('连接信息待更新', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: '验证并开门' }).isDisabled(), true)
  deviceFailure = false

  await page.getByRole('link', { name: '访客', exact: true }).click()
  await page.getByRole('button', { name: '创建访客凭证', exact: true }).click()
  await page.getByLabel('访客名称', { exact: false }).fill('测试来访者')
  await page.getByRole('button', { name: '确认创建', exact: true }).click()
  await page.getByText('one-time-qa-code', { exact: true }).waitFor()
  await page.getByRole('button', { name: '关闭', exact: true }).click()
  assert.equal(await page.getByText('one-time-qa-code', { exact: true }).count(), 0)
  await page.getByRole('button', { name: '撤销', exact: true }).click()
  await page.getByRole('button', { name: '确认撤销', exact: true }).click()
  await page.getByText('已撤销', { exact: true }).waitFor()

  await page.getByRole('link', { name: '成员与权限', exact: true }).click()
  await page.getByLabel('账户状态').selectOption('approved')
  await page.getByRole('button', { name: '管理权限', exact: true }).click()
  await page.getByText('registered_but_not_reported', { exact: true }).waitFor()
  rejectGrant = true
  await page.getByRole('button', { name: '撤销权限', exact: true }).first().click()
  await page.getByText('Device disabled', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: '撤销权限', exact: true }).count(), 2)
  await page.screenshot({ path: path.join(artifacts, 'users-desktop.png'), fullPage: true })
  await page.getByRole('link', { name: '异常提醒', exact: true }).click()
  await page.getByRole('button', { name: '查看与处理', exact: true }).click()
  await page.getByRole('dialog').getByText('未启用', { exact: true }).waitFor()
  await page.keyboard.press('Escape')
  assert.equal(await page.getByRole('dialog').count(), 0)

  for (const width of [320, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    for (const route of [
      '/dashboard',
      '/dashboard/records',
      '/dashboard/guests',
      '/dashboard/alarms',
      '/dashboard/users',
      '/dashboard/security',
      '/dashboard/evidence'
    ]) {
      await page.goto(base + route)
      await page.locator('.page-heading, .home-welcome').waitFor()
      await noOverflow(page, `${route} at ${width}px`)
    }
  }
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(base + '/dashboard')
  await page.getByRole('button', { name: '验证并开门' }).waitFor()
  await page.screenshot({ path: path.join(artifacts, 'doors-mobile.png'), fullPage: true })
  await page.getByRole('link', { name: '设置', exact: true }).click()
  await page.getByRole('heading', { name: '账户与安全', exact: true }).waitFor()
  assert.equal(await page.getByRole('dialog').count(), 0)
  await page.getByLabel('家门', { exact: true }).selectOption('qa_front')
  await page.getByLabel('名称', { exact: true }).fill('入户门')
  await page.getByRole('button', { name: '保存家门名称', exact: true }).click()
  await page.getByText('家门名称已保存', { exact: true }).waitFor()
  await page.goto(base + '/dashboard/evidence')
  await page.getByText('SL-SEC-v3', { exact: true }).waitFor()
  await noOverflow(page, 'security evidence mobile')
  await page.goto(base + '/dashboard')
  await page.locator('#device-select').waitFor()
  assert.ok((await page.locator('#device-select').textContent()).includes('入户门'))
  emptyDevices = true
  await page.getByRole('button', { name: '刷新状态', exact: true }).click()
  await page.getByText('把你的家门连接进来', { exact: true }).waitFor()
  await noOverflow(page, 'empty home mobile')
  emptyDevices = false
  await page.getByRole('button', { name: '刷新状态', exact: true }).click()
  await page.getByRole('button', { name: '验证并开门' }).waitFor()
  for (const route of [
    '/dashboard',
    '/dashboard/records',
    '/dashboard/guests',
    '/dashboard/security',
    '/dashboard/evidence'
  ]) {
    await page.goto(base + route)
    await page.locator('.page-heading, .home-welcome').waitFor()
    await page.evaluate(() => {
      const sizes = [...document.querySelectorAll('body *')].map((element) => [
        element,
        parseFloat(getComputedStyle(element).fontSize)
      ])
      for (const [element, size] of sizes) element.style.fontSize = `${size * 2}px`
    })
    await noOverflow(page, `${route} mobile text 200%`)
  }
  await page.goto(base + '/dashboard/security')
  await page.getByRole('button', { name: '修改密码', exact: true }).waitFor()

  const guest = await context.newPage()
  await page.getByRole('button', { name: '修改密码', exact: true }).click()
  await page.getByLabel('当前密码', { exact: true }).fill('test-current')
  await page.getByLabel('新密码', { exact: true }).fill('long-new-password')
  await page.getByLabel('确认新密码', { exact: true }).fill('does-not-match')
  await page.getByLabel('身份验证器验证码', { exact: true }).fill('123456')
  await page.getByRole('button', { name: '修改密码并退出', exact: true }).click()
  await page.getByText('两次新密码不一致', { exact: true }).waitFor()
  await page.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('button', { name: '修改密码', exact: true }).click()
  assert.equal(await page.getByLabel('当前密码', { exact: true }).inputValue(), '')
  await page.getByRole('button', { name: '关闭', exact: true }).click()
  guest.on('pageerror', (error) => errors.push(error.message))
  await fixture(guest)
  await guest.setViewportSize({ width: 390, height: 844 })
  await guest.goto(base + '/guest')
  await guest.getByLabel('访客凭证', { exact: true }).fill('qa-guest')
  lostConsumption = true
  await guest.getByRole('button', { name: '验证并申请开门', exact: true }).click()
  await guest.getByText('设备已确认本次命令执行', { exact: true }).waitFor()
  assert.equal(calls.verify, 1, 'lost consumption response must not use a second guest allowance')
  await noOverflow(guest, 'guest mobile')
  await guest.screenshot({ path: path.join(artifacts, 'guest-mobile.png'), fullPage: true })
  await guest.getByRole('button', { name: '验证其他凭证', exact: true }).click()
  await guest.getByLabel('访客凭证', { exact: true }).fill('qa-guest-again')
  receiptUnauthorized = true
  const deniedReceipt = guest.waitForResponse(
    (response) => response.url().endsWith('/api/lock/command-status') && response.status() === 401
  )
  await guest.getByRole('button', { name: '验证并申请开门', exact: true }).click()
  await deniedReceipt
  await guest.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  )
  assert.equal(
    new URL(guest.url()).pathname,
    '/guest',
    'expired capability must not redirect to account login'
  )
  assert.equal(await guest.evaluate(() => localStorage.getItem('token')), 'qa-fixture')
  receiptUnauthorized = false
  const unauthorized = await browser.newContext()
  const publicPage = await unauthorized.newPage()
  await publicPage.goto(base + '/dashboard/users')
  await publicPage.getByRole('heading', { name: '欢迎回家' }).waitFor()
  await publicPage.screenshot({ path: path.join(artifacts, 'login-desktop.png'), fullPage: true })
  assert.deepEqual(errors, [], 'runtime errors or Vue warnings')
  console.log(
    'Browser acceptance passed: login, receipt recovery, state semantics, permissions, visitors, alarms, naming, security evidence, empty state, 35 responsive and 5 text enlargement checks.'
  )
  await browser.close()
}
run().catch(async (error) => {
  console.error(error)
  if (browser) await browser.close()
  process.exitCode = 1
})
