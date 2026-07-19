<script setup>
import { computed, ref } from 'vue'

const file = ref(null)
const maxPages = ref(50)
const report = ref('')
const error = ref('')
const isProcessing = ref(false)
const downloadId = ref('')
const downloadName = ref('')

const fileLabel = computed(() => file.value ? file.value.name : '选择 PDF 文件')
const canSubmit = computed(() => file.value && !isProcessing.value)

function onFileChange(event) {
  const selected = event.target.files?.[0]
  file.value = selected || null
  report.value = ''
  error.value = ''
  downloadId.value = ''
  downloadName.value = ''
}

async function processPdf() {
  if (!file.value) {
    error.value = '请先选择一个 PDF 文件。'
    return
  }

  isProcessing.value = true
  error.value = ''
  report.value = '正在上传并分析 PDF，请稍等...'
  downloadId.value = ''
  downloadName.value = ''

  const form = new FormData()
  form.append('pdf', file.value)
  form.append('max_pages', String(maxPages.value))

  try {
    const response = await fetch('/api/process', {
      method: 'POST',
      body: form,
    })
    const data = await response.json()

    if (!response.ok) {
      throw new Error(data.error || '处理失败，请稍后再试。')
    }

    report.value = data.report
    downloadId.value = data.download_id
    downloadName.value = data.download_name
  } catch (err) {
    report.value = ''
    error.value = err.message || '处理失败，请稍后再试。'
  } finally {
    isProcessing.value = false
  }
}
</script>

<template>
  <main class="app-shell">
    <section class="workspace">
      <div class="intro">
        <p class="eyebrow">PDF Bookmark Builder</p>
        <h1>PDF 智能目录生成器</h1>
        <p class="subtitle">上传 PDF，自动识别章节结构，并生成可点击的书签目录。</p>
      </div>

      <div class="panels">
        <form class="panel input-panel" @submit.prevent="processPdf">
          <label class="upload-box">
            <input type="file" accept="application/pdf,.pdf" @change="onFileChange" />
            <span class="upload-title">{{ fileLabel }}</span>
            <span class="upload-hint">支持文字型 PDF；扫描件会尝试视觉分析</span>
          </label>

          <label class="field">
            <span>分析前 N 页</span>
            <input v-model.number="maxPages" type="range" min="5" max="100" step="5" />
            <strong>{{ maxPages }} 页</strong>
          </label>

          <button class="primary-button" type="submit" :disabled="!canSubmit">
            {{ isProcessing ? '处理中...' : '开始处理' }}
          </button>

          <p class="note">处理时长通常为几十秒到几分钟，取决于 PDF 页数和接口响应速度。</p>
        </form>

        <section class="panel output-panel" aria-live="polite">
          <h2>处理结果</h2>
          <p v-if="!report && !error" class="empty">结果会显示在这里。</p>
          <p v-if="error" class="error">{{ error }}</p>
          <pre v-if="report" class="report">{{ report }}</pre>
          <a v-if="downloadId" class="download-button" :href="`/api/download/${downloadId}`">
            下载处理后的 PDF
          </a>
        </section>
      </div>
    </section>
  </main>
</template>
