<template>
  <span>{{ display }}</span>
</template>

<script setup>
// KPI 数字滚动动画（尊重 prefers-reduced-motion：直接显示终值）
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps({
  value: { type: Number, default: 0 },
  duration: { type: Number, default: 700 },
  format: { type: Function, default: null },   // (v) => string
})

const display = ref('')
let raf = null
const fmt = (v) => (props.format ? props.format(v) : String(Math.round(v)))

function run(to) {
  cancelAnimationFrame(raf)
  if (typeof to !== 'number' || !Number.isFinite(to)) { display.value = '—'; return }
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    display.value = fmt(to)
    return
  }
  const t0 = performance.now()
  const step = (t) => {
    const p = Math.min(1, (t - t0) / props.duration)
    const e = 1 - Math.pow(1 - p, 3)   // easeOutCubic
    display.value = fmt(to * e)
    if (p < 1) raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
}

watch(() => props.value, (v) => run(v), { immediate: true })
onUnmounted(() => cancelAnimationFrame(raf))
</script>
