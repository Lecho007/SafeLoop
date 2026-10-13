<template>
  <div class="wrap">
    <!-- 页头 -->
    <div class="glass hd">
      <div class="logo" v-html="logoIcon"></div>
      <div>
        <h1>SafeLoop <b>安全体检</b></h1>
        <div class="sl-sub">多智能体闭环安全评估 —— 让 AI 智能体替你测试你的大模型</div>
      </div>
      <span class="sp"></span>
      <el-switch v-model="store.expert" active-text="专家模式" />
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="总览" name="overview" />
      <el-tab-pane label="轨迹回放" name="replay" />
      <el-tab-pane label="评估报告" name="report" />
    </el-tabs>

    <Overview v-show="tab === 'overview'" />
    <ReplayView v-show="tab === 'replay'" />
    <ReportView v-show="tab === 'report'" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { icon } from './icons.js'
import { useStore } from './store.js'
import Overview from './components/Overview.vue'
import ReplayView from './components/ReplayView.vue'
import ReportView from './components/ReportView.vue'

const store = useStore()
const tab = ref('overview')
const logoIcon = icon('shield', 22, 'stroke:#ffffff')
</script>
