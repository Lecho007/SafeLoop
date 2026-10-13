// 全局状态：专家模式 / 活动运行轮询 / 当前查看的 run（报告+轨迹）
import { defineStore } from 'pinia'
import { api } from './api'

const ACTIVE_KEY = 'safeloop_active_run'
const TERMINAL = ['COMPLETED', 'FAILED', 'CANCELLED']

export const useStore = defineStore('main', {
  state: () => ({
    expert: false,
    activeRunId: null,
    run: null,          // /evaluations/{id} 行
    live: null,         // { events: [...] }
    timer: null,
    runT0: null,
    pollError: false,   // 连续轮询失败（服务不可达提示）
    lastRun: null,      // 刚结束的 run：{ run_id, status, error }（失败原因展示）
    viewedRunId: null,
    viewedReport: null,
    viewedTrajs: null,
    historyVersion: 0,  // 历史列表刷新信号
  }),
  getters: {
    running: (s) => !!s.activeRunId,
  },
  actions: {
    async submitRun(spec) {
      if (this.activeRunId) throw new Error('已有检测在进行中，请等待完成或先停止')
      const r = await api.submit(spec)
      this.adopt(r.run_id, Date.now())
      return r.run_id
    },
    // 接管一个 run：提交 / 续跑 / 刷新恢复共用
    adopt(runId, t0) {
      this.activeRunId = runId
      this.runT0 = t0
      this.lastRun = null
      this.pollError = false
      sessionStorage.setItem(ACTIVE_KEY, runId)
      this.startPolling()
    },
    // 页面刷新后恢复活动 run（进度不丢）
    async restoreActive() {
      const id = sessionStorage.getItem(ACTIVE_KEY)
      if (!id || this.activeRunId) return
      try {
        const row = await api.getRun(id)
        if (TERMINAL.includes(row.status)) {
          sessionStorage.removeItem(ACTIVE_KEY)
          return
        }
        const t = row.started_at
          ? new Date(String(row.started_at).replace(' ', 'T')).getTime()
          : Date.now()
        this.run = row
        this.adopt(id, Number.isFinite(t) ? t : Date.now())
      } catch (e) { sessionStorage.removeItem(ACTIVE_KEY) }
    },
    startPolling() {
      this.stopPolling()
      let fails = 0
      const tick = async () => {
        if (!this.activeRunId) return
        try {
          this.run = await api.getRun(this.activeRunId)
          this.live = await api.getLive(this.activeRunId)
          fails = 0
          this.pollError = false
          if (TERMINAL.includes(this.run.status)) {
            const id = this.activeRunId
            const row = this.run
            this.stopPolling()
            this.activeRunId = null
            sessionStorage.removeItem(ACTIVE_KEY)
            this.lastRun = { run_id: id, status: row.status, error: row.error || '' }
            // 完成与取消都有（部分）报告；失败不加载产物，原因见 lastRun
            if (row.status !== 'FAILED') {
              try { await this.viewRun(id) } catch (e) { /* 已取消的 run 可能无完整产物 */ }
            }
            this.historyVersion++
          }
        } catch (e) {
          // 网络抖动继续轮询；连续失败才提示服务不可达
          if (++fails >= 5) this.pollError = true
        }
      }
      tick()
      this.timer = setInterval(tick, 2000)
    },
    stopPolling() {
      if (this.timer) clearInterval(this.timer)
      this.timer = null
    },
    async cancelActive() {
      if (!this.activeRunId) return
      await api.cancel(this.activeRunId)
    },
    async resumeRun(runId) {
      await api.resume(runId)
      this.adopt(runId, Date.now())
    },
    // 查看（或完成后加载）一个 run 的报告与轨迹
    async viewRun(runId) {
      const [report, trajs] = await Promise.all([
        api.getReport(runId), api.getTrajectories(runId),
      ])
      this.viewedRunId = runId
      this.viewedReport = report
      this.viewedTrajs = trajs
    },
  },
})
