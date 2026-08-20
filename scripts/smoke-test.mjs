// CAET V1 真实无头浏览器冒烟测试
// 用系统 Chrome + puppeteer-core 加载页面，捕获 console / pageerror，验证路由与 Mock 渲染
import puppeteer from 'puppeteer-core'
import { execSync } from 'node:child_process'

const BASE = 'http://localhost:3000'

// 自动定位 Chrome 路径
function findChrome() {
  const candidates = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ]
  for (const c of candidates) {
    try { execSync(`test -f "${c}"`); return c } catch {}
  }
  return 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
}

const results = []
function log(name, ok, detail = '') {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} | ${name}${detail ? ' | ' + detail : ''}`)
}

const browser = await puppeteer.launch({
  executablePath: findChrome(),
  headless: 'new',
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=390,844'],
})

const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844, isMobile: true })

const consoleErrors = []
const pageErrors = []
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })
page.on('pageerror', (e) => pageErrors.push(e.message))

try {
  // 1. 登录页加载
  await page.goto(BASE + '/login', { waitUntil: 'networkidle0', timeout: 20000 })
  const hasLogin = await page.$('input[type="email"], input[type="text"]')
  log('登录页加载 + 表单渲染', !!hasLogin)
  const bodyText = await page.evaluate(() => document.body.innerText)
  log('登录页含品牌/标题', /CAET|登录|学员|管理员/i.test(bodyText))

  // 2. 快速登录 - 学员
  const quickBtns = await page.$$('button')
  let studentClicked = false
  for (const b of quickBtns) {
    const t = await page.evaluate((el) => el.innerText, b)
    if (/学员/.test(t)) { await b.click(); studentClicked = true; break }
  }
  log('点击"学员"快速登录', studentClicked)
  await new Promise(r => setTimeout(r, 1500))
  const url1 = page.url()
  log('学员登录后路由跳转 /student', /\/student/.test(url1), url1)

  // 3. 学员任务中心渲染（Mock 数据）
  await page.goto(BASE + '/student/tasks', { waitUntil: 'networkidle0', timeout: 20000 })
  await new Promise(r => setTimeout(r, 800))
  const tasksText = await page.evaluate(() => document.body.innerText)
  log('任务中心渲染卡片/标题', /任务|Warm|课程|进度/i.test(tasksText))
  const cardCount = await page.$$eval('[class*="card"], [class*="Card"]', els => els.length).catch(() => 0)
  log('任务中心存在卡片元素', cardCount > 0, `cards=${cardCount}`)

  // 4. 学习记录页（Mock）
  await page.goto(BASE + '/student/record', { waitUntil: 'networkidle0', timeout: 20000 })
  await new Promise(r => setTimeout(r, 600))
  const recText = await page.evaluate(() => document.body.innerText)
  log('学习记录页渲染', /学习|时长|记录|日历/i.test(recText))

  // 5. 管理员端（先登出再切管理员较麻烦，直接 goto admin 路由，靠 mock fallback）
  await page.goto(BASE + '/admin', { waitUntil: 'networkidle0', timeout: 20000 })
  await new Promise(r => setTimeout(r, 800))
  const adminText = await page.evaluate(() => document.body.innerText)
  log('管理员看板渲染', /看板|数据|学员|任务|完成率/i.test(adminText))

  // 6. 管理员任务列表 + 学员列表
  await page.goto(BASE + '/admin/tasks', { waitUntil: 'networkidle0', timeout: 20000 })
  await new Promise(r => setTimeout(r, 500))
  const adminTasks = await page.evaluate(() => document.body.innerText)
  log('管理员任务页渲染', /任务|发布|Warm|截止/i.test(adminTasks))

  await page.goto(BASE + '/admin/learners', { waitUntil: 'networkidle0', timeout: 20000 })
  await new Promise(r => setTimeout(r, 500))
  const adminLearners = await page.evaluate(() => document.body.innerText)
  log('管理员学员页渲染', /学员|工号|分组|完成率/i.test(adminLearners))

  // 7. 横向滚动检查（390px 无横向滚动）
  const overflow = await page.evaluate(() => ({
    sw: document.documentElement.scrollWidth,
    cw: document.documentElement.clientWidth,
  }))
  log('390px 无横向滚动', overflow.sw <= overflow.cw + 2, `scrollW=${overflow.sw} clientW=${overflow.cw}`)

} catch (e) {
  log('测试执行异常', false, e.message)
} finally {
  log('控制台 error 数', consoleErrors.length === 0, `count=${consoleErrors.length}`)
  if (consoleErrors.length) console.log('  console errors:\n   - ' + consoleErrors.slice(0, 10).join('\n   - '))
  log('页面 pageerror 数', pageErrors.length === 0, `count=${pageErrors.length}`)
  if (pageErrors.length) console.log('  page errors:\n   - ' + pageErrors.slice(0, 10).join('\n   - '))
  await browser.close()
  const passed = results.filter(r => r.ok).length
  console.log(`\n==== SMOKE RESULT: ${passed}/${results.length} passed ====`)
  process.exit(passed === results.length ? 0 : 1)
}
