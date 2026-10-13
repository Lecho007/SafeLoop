// SafeLoop 前端零 GPU 冒烟（Playwright Chromium）
// 前置：Web 服务已启动（默认 http://127.0.0.1:8712，可用 SAFELOOP_URL 覆盖）
// 运行：npm run smoke
// playwright 解析：优先本项目 node_modules；否则设 PLAYWRIGHT_PKG 指向一个
// 已 npm i playwright 的目录里的 package.json（Windows 侧建议本地盘目录，
// 例如 PLAYWRIGHT_PKG=D:/ZcodeData/safeloop-smoke/package.json）。
import { createRequire } from 'node:module'

let chromium
try {
  ({ chromium } = await import('playwright'))
} catch {
  const base = process.env.PLAYWRIGHT_PKG
  if (!base) throw new Error('本地无 playwright，且未设置 PLAYWRIGHT_PKG')
  ;({ chromium } = createRequire(base)('playwright'))
}

const BASE = process.env.SAFELOOP_URL || 'http://127.0.0.1:8712'
const results = []
let failed = 0
const ok = (name, cond, extra = '') => {
  results.push(`${cond ? 'PASS' : 'FAIL'}  ${name}${extra ? '  [' + extra + ']' : ''}`)
  if (!cond) failed++
}

// 优先复用系统 Edge（Windows 自带，零下载）；无 Edge 时回退 Playwright
// 自带 Chromium（首次需 npx playwright install chromium）
let browser
try {
  browser = await chromium.launch({ channel: 'msedge' })
} catch {
  browser = await chromium.launch()
}
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })

try {
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1200)
  ok('首页标题', (await page.title()).includes('SafeLoop'))
  ok('向导双卡', (await page.getByText('检测对象').count()) >= 1
    && (await page.getByText('检测方式与范围').count()) >= 1)
  ok('架构图渲染', (await page.locator('.hd-svg').count()) === 1)
  ok('历史列表加载', (await page.locator('.hrow').count()) >= 1)

  // 示例数据 → 三页内容
  await page.getByRole('button', { name: '载入示例数据' }).click()
  await page.waitForTimeout(1800)
  ok('示例数据载入（风险发现区激活）',
    (await page.getByText('发现风险场景').count()) >= 1)

  await page.getByRole('tab', { name: '评估报告' }).click()
  await page.waitForTimeout(800)
  ok('报告等级徽章卡', (await page.getByText('风险发现率').count()) >= 1)
  ok('导出/存档按钮', (await page.getByRole('button', { name: '导出 HTML 报告' }).count()) === 1
    && (await page.getByRole('button', { name: '下载对话存档' }).count()) === 1)

  await page.getByRole('tab', { name: '轨迹回放' }).click()
  await page.waitForTimeout(900)
  const bar = page.locator('.rp-bar')
  const barTxt = (await bar.count()) === 1 ? await bar.innerText() : ''
  ok('回放全量列表+计数', /共 \d+ 条 · 风险 \d+ · 抵御 \d+/.test(barTxt), barTxt.split('\n')[0])
  const links = await page.locator('.tx-link').count()
  ok('全文入口出现', links >= 1, `${links} 个`)
  if (links) {
    await page.locator('.tx-link').first().click()
    await page.waitForTimeout(600)
    ok('全文弹窗打开', (await page.getByRole('button', { name: '复制全文' }).count()) === 1)
    await page.locator('.el-dialog').first().press('Escape')
    await page.waitForTimeout(400)
  }

  await page.getByRole('tab', { name: '总览' }).click()
  await page.locator('.el-segmented__item').filter({ hasText: '指定场景' }).first().click()
  await page.waitForTimeout(1000)
  const catVal = await page.evaluate(() => {
    const spans = document.querySelectorAll('.form-card .el-select__placeholder span')
    return spans.length ? spans[0].textContent.trim() : ''
  })
  ok('指定场景类别加载', catVal.length > 0, catVal || '空')
} catch (e) {
  failed++
  results.push('FAIL  异常中断: ' + e.message)
  await page.screenshot({ path: 'tests/smoke-error.png', fullPage: true }).catch(() => {})
} finally {
  console.log('\n===== SafeLoop 前端冒烟（' + BASE + '）=====')
  results.forEach(r => console.log(r))
  console.log('===== ' + (failed ? failed + ' 项失败（见 tests/smoke-error.png）' : '全部通过') + ' =====')
  await browser.close()
  process.exit(failed ? 1 : 0)
}
