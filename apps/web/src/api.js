// FastAPI 客户端（同源部署；开发态经 vite 代理到 8712）
// 鉴权：服务端启用 SAFELOOP_API_KEY 时，密钥存 localStorage 并附 X-API-Key 头
const apiKey = () => localStorage.getItem('safeloop_api_key') || ''
const headersWithKey = (headers = {}) =>
  apiKey() ? { 'X-API-Key': apiKey(), ...headers } : headers

const fail = async (r) => {
  let detail = r.statusText
  try { detail = (await r.json()).detail || detail } catch (e) { /* noop */ }
  throw new Error(detail)
}

const j = async (url, opts) => {
  const r = await fetch(url, { ...opts, headers: headersWithKey(opts?.headers) })
  if (!r.ok) await fail(r)
  return r.json()
}

// 文件下载（导出报告 / 对话存档）：blob → <a download>，优先服务端文件名
const download = async (url, fallbackName) => {
  const r = await fetch(url, { headers: headersWithKey() })
  if (!r.ok) await fail(r)
  const blob = await r.blob()
  const cd = r.headers.get('content-disposition') || ''
  const m = cd.match(/filename="?([^";]+)"?/)
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = m ? decodeURIComponent(m[1]) : fallbackName
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 5000)
}

export const api = {
  get: (url) => j(url),
  submit: (spec) => j('/evaluations', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(spec),
  }),
  getRun: (id) => j(`/evaluations/${id}`),
  getLive: (id) => j(`/evaluations/${id}/live?tail=200`),
  cancel: (id) => j(`/evaluations/${id}/cancel`, { method: 'POST' }),
  resume: (id) => j(`/evaluations/${id}/resume`, { method: 'POST' }),
  listRuns: (limit = 30) => j(`/runs?limit=${limit}`),
  getReport: (id) => j(`/evaluations/${id}/report`),
  getTrajectories: (id) => j(`/evaluations/${id}/trajectories`),
  testConnection: (cfg) => j('/targets/test-connection', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  }),
  replay: (runId = 'stage1b_r_4060') =>
    j(`/replay?run_id=${encodeURIComponent(runId)}`, { method: 'POST' }),
  exportHtml: (id) => download(`/evaluations/${id}/export`, `${id}_report.html`),
  transcript: (id) => download(`/evaluations/${id}/transcript`, `${id}_transcript.md`),
  setReviewed: (id, reviewed) => j(`/evaluations/${id}/reviewed`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reviewed }),
  }),
  getAnalysis: (id) => j(`/evaluations/${id}/analysis`),
  analyzeReport: (id, message = '', reset = false) =>
    j(`/evaluations/${id}/analyze`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, reset }),
    }),
}
