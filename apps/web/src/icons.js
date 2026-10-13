// 内嵌线性图标（与 GUI v3 同源，零外链）
const ICONS = {
  shield: '<path d="M12 3l7 3v5c0 4.6-3 7.6-7 9-4-1.4-7-4.4-7-9V6z"/><path d="M9.5 11.5l2 2 3.5-3.5"/>',
  play: '<path d="M8 5l11 7-11 7z" fill="currentColor" stroke="none"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none"/>',
  doc: '<path d="M6 3h9l4 4v14H6z"/><path d="M9 12h6M9 16h6"/>',
  pulse: '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
  terminal: '<path d="M4 5h16v14H4z"/><path d="M7 9l3 3-3 3M13 15h4"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  cpu: '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
  alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v4M12 17.5v.5"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  tree: '<path d="M12 3v4M6 21v-4M18 21v-4M12 13v4M6 13h12"/><circle cx="12" cy="9" r="2"/><circle cx="6" cy="15" r="2"/><circle cx="18" cy="15" r="2"/><circle cx="12" cy="19" r="2"/>',
  history: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M4 19h16"/>',
}

export function icon(name, size = 16, extra = '') {
  return `<svg class="ic" style="width:${size}px;height:${size}px;${extra}" viewBox="0 0 24 24">${
    ICONS[name] || ''}</svg>`
}

export const CATEGORY_ZH = {
  Disinformation: '虚假信息', 'Economic harm': '经济损害',
  'Expert advice': '冒充专家', 'Fraud/Deception': '欺诈骗术',
  'Government decision-making': '政务操纵', 'Harassment/Discrimination': '骚扰歧视',
  'Malware/Hacking': '恶意软件与入侵', 'Physical harm': '人身伤害',
  Privacy: '隐私侵犯', 'Sexual/Adult content': '成人内容',
}
export const zhCat = (k) => CATEGORY_ZH[String(k || '').replace('JBB:', '')] || k
