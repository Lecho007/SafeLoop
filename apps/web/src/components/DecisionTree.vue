<template>
  <div v-html="svg"></div>
</template>

<script setup>
import { computed } from 'vue'
import { decisionPathTree } from '../tree.js'

const props = defineProps({
  rounds: { type: Array, default: () => [] },
  verdict: { type: String, default: null },
  triggerRound: { type: Number, default: null },
  progress: { type: Number, default: null },
})
const svg = computed(() =>
  decisionPathTree(props.rounds, props.verdict, true, props.triggerRound, props.progress))
</script>
