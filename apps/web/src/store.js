// 全局状态：专家模式 / 活动运行轮询 / 当前查看的 run（报告+轨迹）
import { defineStore } from 'pinia'
import { api } from './api'

export const useStore = defineStore('main', {
  state: () => ({
    expert: false,
    activeRunId: null,
    run: null,          // /evaluations/{id} 行
    live: null,         // { events: [...] }
    timer: null,
    runT0: null,
    viewedRunId: null,
    viewedReport: null,
    viewedTrajs: null,
    viewedIsDemo: false,
    historyVersion: 0,  // 历史列表刷新信号
  }),
  getters: {
    running: (s) => !!s.activeRunId,
  },
  actions: {
    async submitRun(spec) {
      const r = await api.submit(spec)
      this.activeRunId = r.run_id
      this.runT0 = Date.now()
      this.startPolling()
      return r.run_id
    },
    startPolling() {
      this.stopPolling()
      const tick = async () => {
        if (!this.activeRunId) return
        try {
          this.run = await api.getRun(this.activeRunId)
          this.live = await api.getLive(this.activeRunId)
          if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(this.run.status)) {
            const id = this.activeRunId
            this.stopPolling()
            if (this.run.status === 'COMPLETED') await this.viewRun(id)
            this.activeRunId = null
            this.historyVersion++
          }
        } catch (e) { /* 网络抖动继续轮询 */ }
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
    // 查看（或完成后加载）一个 run 的报告与轨迹
    async viewRun(runId) {
      const [report, trajs] = await Promise.all([
        api.getReport(runId), api.getTrajectories(runId),
      ])
      this.viewedRunId = runId
      this.viewedReport = report
      this.viewedTrajs = trajs
      this.viewedIsDemo = false
    },
  },
})
