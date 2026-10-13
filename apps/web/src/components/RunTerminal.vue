<template>
  <div class="term">
    <div class="term-head">
      <span class="dot" v-if="liveDot"></span>
      <slot name="head"></slot>
      <span class="term-legend" v-if="legend" title="每轮信号点语义">
        <span class="lg"><i class="r"></i>风险确认</span>
        <span class="lg"><i class="a"></i>裁判注意</span>
        <span class="lg"><i class="g"></i>安全</span>
      </span>
      <span class="right" :class="{ squeezed: legend }" v-if="right" :title="rightTitle">{{ right }}</span>
    </div>
    <div class="term-body">
      <slot></slot>
    </div>
  </div>
</template>

<script setup>
defineProps({
  liveDot: { type: Boolean, default: true },
  right: { type: String, default: '' },
  rightTitle: { type: String, default: '' },
  legend: { type: Boolean, default: false },   // 信号点图例（红/琥珀/绿）
})
</script>
