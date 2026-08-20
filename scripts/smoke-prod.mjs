// CAET 生产版前端冒烟：验证改造后不再依赖 Supabase、不白屏、错误被捕获
import puppeteer from 'puppeteer-core'
import fs from 'fs'

const URL = 'http://localhost:4173/'
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
})
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

const pageErrors = []
const consoleErrors = []
page.on('pageerror', (e) => pageErrors.push(e.message))
page.on('console', (m) => {
  if (m.type() === 'error') consoleErrors.push(m.text())
})

await page.goto(URL, { waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {})
await new Promise((r) => setTimeout(r, 1500))

const bodyText = await page.evaluate(() => document.body.innerText.trim().slice(0, 200))
const hasForm = await page.evaluate(() => !!document.querySelector('input,button'))

// 尝试点击登录相关按钮（无后端时预期失败但不白屏）
const clicked = await page.evaluate(() => {
  const btns = [...document.querySelectorAll('button')]
  const target = btns.find((b) => /学员|管理员|登录/.test(b.innerText))
  if (target) {
    target.click()
    return target.innerText.trim()
  }
  return null
})
await new Promise((r) => setTimeout(r, 2500))

const afterText = await page.evaluate(() => document.body.innerText.trim().slice(0, 200))
const noPageError = pageErrors.length === 0
const noSupabaseErr = !consoleErrors.some((e) => /supabase/i.test(e))
// 无横向滚动（390 视口）
const noHScroll = await page.evaluate(() => document.documentElement.scrollWidth <= 400)

const result = {
  bodyText,
  hasForm,
  clickedButton: clicked,
  afterLoginText: afterText,
  noPageError,
  pageErrors,
  noSupabaseErr,
  consoleErrors: consoleErrors.slice(0, 5),
  noHScroll,
}
console.log(JSON.stringify(result, null, 2))

await page.screenshot({ path: '/tmp/caet_prod_smoke.png' }).catch(() => {})
await browser.close()
process.exit(noPageError && noSupabaseErr ? 0 : 1)
