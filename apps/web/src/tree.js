// 决策路径树 SVG 生成器 —— 自 apps/workbench/components/tree_svg.py 1:1 移植
const LENS = '#4d6bfe', RISK = '#e5484d', WARN = '#d97706', SAFE = '#12a150'
const PANEL = '#ffffff', TRACE = '#dfe5ee'
const SIGNAL_HEX = { risk: RISK, warn: WARN, safe: SAFE, null: '#9db0c4' }
const ACTION_ZH = { KEEP: '保持', REFINE: '细化', SWITCH: '换策略', REALIGN: '回正', UNCERTAIN: '不确定' }
const STRATEGY_ZH = {
  direct: '直接提问', roleplay: '角色扮演', reframing: '换角度提问',
  obfuscation: '混淆表述', multi_turn: '分步引导',
}

export function decisionPathTree(rounds, verdict = null, live = false,
                                  triggerRound = null, progress = null) {
  if (!rounds || !rounds.length) {
    return `<div style='color:#67738a;padding:20px;text-align:center'>
      决策树将在任务开始后逐轮生长</div>`
  }
  const n = rounds.length
  const w = Math.max(760, n * 180 + 80), h = 240
  const gap = (w - 120) / Math.max(1, n)
  const parts = [
    `<svg viewBox="0 0 ${w} ${h}" width="100%">`,
    `<defs><filter id="dglow" x="-60%" y="-60%" width="220%" height="220%">
      <feDropShadow dx="0" dy="0" stdDeviation="6" flood-color="${LENS}"/></filter></defs>`,
    `<style>.dn{fill:${PANEL};stroke:${TRACE};stroke-width:1.5}
.dn.done{fill:#eef1ff;stroke:${LENS};stroke-width:2}
.dt{font-size:13px;font-weight:600;fill:#172033}
.ds{font-size:11px;fill:#67738a}
.de{stroke:${'#c9d6e6'};stroke-width:2;fill:none}
.de.done{stroke:${LENS};stroke-width:2.4;stroke-dasharray:6 12;
animation:deflow 1s linear infinite;filter:drop-shadow(0 0 4px rgba(47,111,235,.5))}
@keyframes deflow{to{stroke-dashoffset:-18}}
.dl{font-size:12px;font-weight:600;fill:${LENS}}
.dl.dim{fill:#9db0c4}</style>`,
  ]
  rounds.forEach((nd, i) => {
    const cx = 70 + Math.trunc(gap * i)
    const sig = SIGNAL_HEX[nd.signal ?? null] || SIGNAL_HEX.null
    const state = nd.state || 'decided'
    const done = progress != null && i < progress
    let stroke = sig
    if (progress != null) stroke = done ? sig : '#c9d6e6'
    const nodeCls = done ? ' class="dn done"' : ' class="dn"'
    parts.push(`<circle cx="${cx}" cy="70" r="30"${nodeCls}
      fill="${done ? '#eef1ff' : PANEL}" stroke="${stroke}" stroke-width="2.4"/>`)
    if (nd.signal) parts.push(`<circle cx="${cx}" cy="70" r="8" fill="${sig}"/>`)
    if (triggerRound && nd.round === triggerRound) {
      parts.push(`<circle cx="${cx}" cy="70" r="36" fill="none" stroke="${RISK}"
        stroke-width="2" stroke-dasharray="4 4"/>
        <text x="${cx}" y="34" text-anchor="middle" fill="${RISK}"
        font-size="11" font-weight="700">触发</text>`)
    }
    parts.push(`<text x="${cx}" y="120" text-anchor="middle" class="dt">第${nd.round ?? i + 1}轮</text>`)
    if (nd.strategy) {
      parts.push(`<text x="${cx}" y="138" text-anchor="middle" class="ds">${
        STRATEGY_ZH[nd.strategy] || nd.strategy}</text>`)
    }
    const sigtxt = { risk: '推进显著', warn: '部分推进', safe: '未推进' }[nd.signal] || ''
    if (sigtxt) {
      parts.push(`<text x="${cx}" y="156" text-anchor="middle" class="ds"
        fill="${sig}">${sigtxt}</text>`)
    }
    if (i < n - 1 && nd.action) {
      const zh = ACTION_ZH[nd.action] || nd.action
      const x1 = cx + 32, x2 = cx + Math.trunc(gap) - 32
      const edgeDone = progress != null && i + 1 < progress
      parts.push(`<path class="de${edgeDone ? ' done' : ''}" d="M${x1} 70 L ${x2} 70"/>`)
      parts.push(`<text x="${(x1 + x2) / 2}" y="60" text-anchor="middle"
        class="dl${progress != null && !edgeDone ? ' dim' : ''}">${zh}</text>`)
    }
  })
  if (verdict) {
    const vc = verdict.includes('风险') ? RISK : SAFE
    parts.push(`<rect x="${w - 170}" y="185" width="150" height="34" rx="17"
      fill="${vc}" fill-opacity="0.16" stroke="${vc}" stroke-width="1.5"/>`)
    parts.push(`<text x="${w - 95}" y="207" text-anchor="middle" fill="${vc}"
      font-size="14" font-weight="700">⚖️ ${verdict}</text>`)
  }
  parts.push('</svg>')
  return parts.join('')
}

// 实况事件 → 树节点（与 GUI 版 events 映射同义）
export function liveEventsToRounds(events) {
  const seen = {}
  events.forEach(e => { seen[e.round] = e })
  return Object.keys(seen).map(Number).sort((a, b) => a - b).map(r => {
    const e = seen[r]
    const adv = e.advancement, safety = e.safety
    let signal = null
    if (adv === 'STRONG') signal = 'risk'
    else if (adv === 'PARTIAL' || safety === 'Unsafe') signal = 'warn'
    else if (adv === 'NONE' || safety === 'Safe') signal = 'safe'
    return { round: r, strategy: e.strategy, signal, action: e.action, state: 'decided' }
  })
}

// 回放轨迹 steps（/trajectories 的 dict 形态）→ 树节点
export function stepsToRounds(steps) {
  return steps.map(s => {
    const meta = (s.judge_output && s.judge_output.metadata) || {}
    const adv = meta.advancement, safety = meta.safety
    let signal = null
    if (adv === 'STRONG') signal = 'risk'
    else if (adv === 'PARTIAL' || safety === 'Unsafe') signal = 'warn'
    else if (adv === 'NONE' || safety === 'Safe') signal = 'safe'
    return {
      round: s.round_id + 1, strategy: s.action.strategy, signal,
      action: s.feedback ? s.feedback.adaptation_action : null,
      state: 'decided',
    }
  })
}

export { STRATEGY_ZH }
