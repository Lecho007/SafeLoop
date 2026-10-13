<template>
  <div class="term">
    <div class="term-head">
      <span class="dot" v-if="liveDot"></span>
      <slot name="head"></slot>
      <span class="right" v-if="right" :title="rightTitle">{{ right }}</span>
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
})
</script>
