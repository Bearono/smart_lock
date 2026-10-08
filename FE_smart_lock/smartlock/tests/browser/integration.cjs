// Run ONLY against tests/browser_fixture.py's disposable database.
const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const { chromium } = require('playwright')
if (process.env.ISOLATED_BACKEND_FIXTURE !== '1') {
  throw new Error('Start the disposable backend fixture, then set ISOLATED_BACKEND_FIXTURE=1')
}
const base = process.env.FRONTEND_URL || 'http://127.0.0.1:5173'
function totp(secret) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  const bits = [...secret.toUpperCase()]
    .map((c) => alphabet.indexOf(c).toString(2).padStart(5, '0'))
    .join('')
  const bytes = []
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2))
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)))
  const hash = crypto.createHmac('sha1', Buffer.from(bytes)).update(counter).digest()
  const offset = hash[19] & 15
  return ((hash.readUInt32BE(offset) & 0x7fffffff) % 1000000).toString().padStart(6, '0')
}
let browser
async function run() {
  browser = await chromium.launch({
    headless: true,
    ...(process.env.BROWSER_CHANNEL ? { channel: process.env.BROWSER_CHANNEL } : {})
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto(base)
  await page.getByLabel('用户名', { exact: true }).fill('qa_operator')
  await page.getByLabel('密码', { exact: true }).fill('local-qa-password')
  const prelogin = page.waitForResponse((response) => response.url().endsWith('/api/login/pre'))
  await page.getByRole('button', { name: '继续验证' }).click()
  const enrollment = await (await prelogin).json()
  assert.equal(enrollment.totp_bound, false, 'fixture must be newly created')
  assert.ok(enrollment.secret)
  await page.getByLabel('身份验证器验证码', { exact: true }).fill(totp(enrollment.secret))
  await page.getByRole('button', { name: '完成绑定并登录' }).click()
  await page.getByRole('button', { name: '上锁', exact: true }).waitFor()
  assert.ok(await page.locator('#device-select').inputValue())
  const receiptResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/lock/control')
  )
  await page.getByRole('button', { name: '上锁', exact: true }).click()
  const receipt = await (await receiptResponse).json()
  assert.equal(receipt.command_accepted, true)
  assert.equal(receipt.hardware_confirmed, false)
  await page.getByText('命令已提交，正在等待设备执行确认', { exact: true }).waitFor()
  await page.getByRole('link', { name: '动态', exact: true }).click()
  await page.getByText('上锁命令已提交', { exact: true }).waitFor()
  assert.equal(await page.getByText('设备已确认本次命令执行', { exact: true }).count(), 0)
  await page.getByRole('link', { name: '访客', exact: true }).click()
  await page.getByRole('button', { name: '创建访客凭证' }).click()
  await page.getByLabel('访客名称', { exact: false }).fill('隔离验收访客')
  await page.getByRole('button', { name: '确认创建' }).click()
  const passCode = await page.locator('.secret-code').textContent()
  await page.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('button', { name: '撤销', exact: true }).click()
  await page.getByRole('button', { name: '确认撤销' }).click()
  await page.getByText('已撤销', { exact: true }).waitFor()
  await page.goto(base + '/guest')
  await page.getByLabel('访客凭证', { exact: true }).fill(passCode.trim())
  await page.getByRole('button', { name: '验证并申请开门' }).click()
  await page.locator('[role="alert"]').waitFor()
  assert.equal(await page.locator('.command-status').count(), 0)
  assert.deepEqual(errors, [])
  console.log(
    'Real backend integration passed: initial TOTP enrollment, authenticated device list, lock receipt, audit history, guest creation/revocation, revoked guest rejection. No simulated execution success.'
  )
  await browser.close()
}
run().catch(async (error) => {
  console.error(error)
  if (browser) await browser.close()
  process.exitCode = 1
})
