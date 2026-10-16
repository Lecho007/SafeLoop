// 轻量 hash 路由(无 vue-router 依赖):#/home #/workbench #/replay #/report #/docs
import { ref } from 'vue'

const route = ref(location.hash.replace(/^#\/?/, '') || 'home')

window.addEventListener('hashchange', () => {
  route.value = location.hash.replace(/^#\/?/, '') || 'home'
})

export function goto(name) {
  location.hash = '#/' + name
}

export function useRoute() {
  return route
}

export const NAV = [
  { key: 'home', label: '首页', hash: '#/home' },
  { key: 'product', label: '产品介绍', hash: '#/product' },
  { key: 'workbench', label: '检测工作台', hash: '#/workbench' },
  { key: 'replay', label: '轨迹回放', hash: '#/replay' },
  { key: 'report', label: '评估报告', hash: '#/report' },
  { key: 'docs', label: '使用文档', hash: '#/docs' },
]
