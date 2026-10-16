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
  ok('Hero 快捷入口卡排', (await page.locator('.hq-card').count()) === 4)
  ok('能力卡片网格(8张4列小卡)', (await page.locator('.cap-card').count()) === 8)
  ok('能力卡彩色标签', (await page.locator('.cc-tag').count()) >= 4)
  ok('四步流程浅灰区块', (await page.locator('.sf-item').count()) === 4)
  ok('数据亮点行', (await page.locator('.num-item').count()) === 4)
  ok('深色页脚', (await page.locator('.site-ft .ft-col').count()) === 4)
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

  // ---- 报告页空态:演示报告选择 ----
  await goto('report')
  ok('报告空态演示卡(3份,均有效源)', (await page.locator('.dr-card').count()) === 3)
  ok('历史报告板块', (await page.locator('.hist-rpts .hrow').count()) >= 1)
  await page.locator('.dr-card').first().getByRole('button', { name: '查看这份报告' }).click()
  await page.waitForTimeout(2000)
  ok('演示卡载入出报告', (await page.locator('.grade-card').count()) === 1)
  ok('返回按钮出现并可回选择态', (await page.getByRole('button', { name: '换一份报告' }).count()) >= 1)
  await page.getByRole('button', { name: '换一份报告' }).click()
  await page.waitForTimeout(500)
  ok('返回后演示卡重新出现', (await page.locator('.dr-card').count()) === 3)
  await page.locator('.hist-rpts .hrow').first().getByRole('button').click()
  await page.waitForTimeout(2000)
  ok('历史报告直接切换成功', (await page.locator('.grade-card').count()) === 1)

  // ---- 演示报告(首页 CTA → 报告页) ----
  await goto('home')
  await page.getByRole('button', { name: '查看示例报告' }).click()
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
  ok('文档页区块指引表', (await page.locator('.dt-row').count()) >= 6)
  ok('文档页无命令块(纯页面操作)', (await page.locator('.doc-code').count()) === 0)
  ok('文档页三步上手', (await page.getByText('三步上手').count()) >= 1)
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
