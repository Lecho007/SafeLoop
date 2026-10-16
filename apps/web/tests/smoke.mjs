// SafeLoop 前端零 GPU 冒烟（Playwright Chromium/Edge）
// 多页面站点结构版:hash 路由 #/home #/product #/workbench #/replay #/report #/docs
// 前置：Web 服务已启动（默认 http://127.0.0.1:8712，SAFELOOP_URL 可覆盖）
// 运行：npm run smoke；playwright 解析：本地 node_modules 或 PLAYWRIGHT_PKG 指向
// 一个已 npm i playwright 的目录里的 package.json（优先系统 Edge，零下载）。
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

let browser
try {
  browser = await chromium.launch({ channel: 'msedge' })
} catch {
  browser = await chromium.launch()
}
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const goto = async (hash) => {
  await page.goto(BASE + '/#' + hash, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(900)
}

try {
  // ---- 首页 ----
  await goto('home')
  ok('首页标题', (await page.title()).includes('SafeLoop'))
  ok('通栏导航', (await page.locator('.site-hd .nav a').count()) === 6)
  ok('Hero 大标题', (await page.locator('.hero h1').count()) === 1
    && (await page.locator('.hero h1').innerText()).includes('替你测试'))
  ok('能力卡片网格', (await page.locator('.cap-card').count()) >= 6)
  ok('底部 CTA（首页/产品页共用组件）', (await page.locator('.cta-band').count()) >= 1)

  // ---- 产品介绍页 ----
  await goto('product')
  ok('产品页架构图', (await page.locator('.hd-svg').count()) === 1)
  ok('角色卡四张', (await page.locator('.role-card').count()) === 4)
  ok('工程红线', (await page.locator('.rule').count()) === 4)

  // ---- 工作台 ----
  await goto('workbench')
  ok('工作台向导双卡', (await page.getByText('检测对象').count()) >= 1
    && (await page.getByText('检测方式与范围').count()) >= 1)
  ok('历史列表加载', (await page.locator('.hrow').count()) >= 1)

  // 指定场景(工作台内)
  await page.locator('.el-segmented__item').filter({ hasText: '指定场景' }).first().click()
  await page.waitForTimeout(1000)
  const catVal = await page.evaluate(() => {
    const spans = document.querySelectorAll('.form-card .el-select__placeholder span')
    return spans.length ? spans[0].textContent.trim() : ''
  })
  ok('指定场景类别加载', catVal.length > 0, catVal || '空')

  // ---- 演示报告(首页 CTA → 报告页) ----
  await goto('home')
  await page.getByRole('button', { name: '查看演示报告' }).click()
  await page.waitForTimeout(2200)
  ok('演示 CTA 跳转报告页', (await page.locator('.grade-card').count()) === 1)
  ok('报告等级徽章卡', (await page.getByText('风险发现率').count()) >= 1)
  ok('导出/存档按钮', (await page.getByRole('button', { name: '导出 HTML 报告' }).count()) === 1
    && (await page.getByRole('button', { name: '下载对话存档' }).count()) === 1)

  // ---- 回放页 ----
  await goto('replay')
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
  }

  // ---- 文档页 ----
  await goto('docs')
  ok('文档页速查表', (await page.locator('.dt-row').count()) >= 10)
  ok('文档启动命令块', (await page.locator('.doc-code').count()) === 1)
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
