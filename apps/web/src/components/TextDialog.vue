<template>
  <el-dialog v-model="show" :title="title" width="720px" top="7vh" append-to-body>
    <div class="tx-pre">{{ text }}</div>
    <template #footer>
      <span class="sl-meta" style="float:left">{{ text.length }} 字符</span>
      <el-button size="small" @click="copy">复制全文</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
// 终端全文查看弹窗：总览实况与回放页的截断 prompt/response「全文」入口共用
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const show = ref(false)
const text = ref('')
const title = ref('全文')

function open(t, tTitle = '全文') {
  text.value = String(t ?? '')
  title.value = tTitle
  show.value = true
}
async function copy() {
  try {
    await navigator.clipboard.writeText(text.value)
    ElMessage.success('已复制到剪贴板')
  } catch (e) { ElMessage.error('复制失败，请在弹窗内手动选择复制') }
}
defineExpose({ open })
</script>

<style scoped>
.tx-pre { max-height: 60vh; overflow: auto; white-space: pre-wrap; word-break: break-word;
  background: #0d1526; color: #c7d5e8; border-radius: 12px; padding: 16px 18px;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 13px;
  line-height: 1.75; }
</style>
