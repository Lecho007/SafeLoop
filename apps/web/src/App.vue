<template>
  <div>
    <div class="wrap">
      <SiteHeader />
      <HomeView v-show="route === 'home'" />
      <ProductView v-show="route === 'product'" />
      <Overview v-show="route === 'workbench'" />
      <ReplayView v-show="route === 'replay'" />
      <ReportView v-show="route === 'report'" />
      <DocsView v-show="route === 'docs'" />
    </div>
    <SiteFooter />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useStore } from './store.js'
import { useRoute } from './router.js'
import SiteHeader from './components/SiteHeader.vue'
import SiteFooter from './components/SiteFooter.vue'
import HomeView from './components/HomeView.vue'
import ProductView from './components/ProductView.vue'
import DocsView from './components/DocsView.vue'
import Overview from './components/Overview.vue'
import ReplayView from './components/ReplayView.vue'
import ReportView from './components/ReportView.vue'

const store = useStore()
const route = useRoute()

// 刷新页面后恢复活动 run 的轮询（进度不丢）
onMounted(() => store.restoreActive())
</script>
