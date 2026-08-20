import puppeteer from 'puppeteer-core'
import { existsSync } from 'fs'

const BASE = process.env.PROD_URL || 'https://301ff87b38ec445bbe03c814ae708514.app.workbuddy.link'

function findChrome() {
  const candidates = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ]
  for (const c of candidates) {
    try { if (existsSync(c)) return c } catch {}
  }
  return undefined
}

const results = []
function record(name, ok, detail = '') {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  -- ' + detail : ''}`)
}

const browser = await puppeteer.launch({
  headless: 'new',
  executablePath: findChrome(),
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
})

try {
  const page = await browser.newPage()
  await page.setViewport({ width: 390, height: 844 })
  const pageErrors = []
  const consoleErrors = []
  page.on('pageerror', (e) => pageErrors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })

  await page.goto(BASE, { waitUntil: 'networkidle0', timeout: 30000 })
  await new Promise(r => setTimeout(r, 1200))

  // 登录页应渲染
  const hasLoginText = await page.evaluate(() => document.body.innerText.includes('登录') || document.body.innerText.includes('CAET'))
  record('登录页渲染', hasLoginText)

  // 点击"学员"快速登录
  const clicked = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')].find(b => /学员/.test(b.innerText))
    if (btn) { btn.click(); return true }
    return false
  })
  record('找到学员快速登录按钮', clicked)
  await new Promise(r => setTimeout(r, 1500))

  const urlAfter = page.url()
  const onTasks = /student|tasks/i.test(urlAfter)
  record('跳转至学员任务页', onTasks, urlAfter)

  // 任务卡片数
  const cardCount = await page.evaluate(() => document.querySelectorAll('[class*="card"]').length)
  record('任务卡片渲染(>0)', cardCount > 0, `${cardCount} 个`)

  record('无 pageerror', pageErrors.length === 0, pageErrors.join(' | '))
  record('无 console error', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '))

  // 横向滚动检查
  const noHScroll = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)
  record('390px 无横向滚动', noHScroll)
} catch (e) {
  record('脚本异常', false, String(e))
} finally {
  await browser.close()
}

const failed = results.filter(r => !r.ok)
console.log(`\n=== 结果: ${results.length - failed.length}/${results.length} 通过 ===`)
process.exit(failed.length ? 1 : 0)
