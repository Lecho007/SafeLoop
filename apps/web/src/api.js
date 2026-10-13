// FastAPI 客户端（同源部署；开发态经 vite 代理到 8712）
const j = async (url, opts) => {
  const r = await fetch(url, opts)
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail || detail } catch (e) { /* noop */ }
    throw new Error(detail)
  }
  return r.json()
}

export const api = {
  get: (url) => j(url),
  submit: (spec) => j('/evaluations', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(spec),
  }),
  getRun: (id) => j(`/evaluations/${id}`),
  getLive: (id) => j(`/evaluations/${id}/live`),
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
}
