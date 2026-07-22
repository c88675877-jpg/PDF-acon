<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  FileUp,
  LoaderCircle,
  RotateCcw,
  Settings2,
} from '@lucide/vue'

const file = ref(null)
const maxPages = ref(50)
const report = ref('')
const error = ref('')
const isProcessing = ref(false)
const uploadProgress = ref(0)
const jobProgress = ref(0)
const jobStep = ref('')
const jobId = ref('')
const downloadUrl = ref('')
const largeFileThreshold = 30 * 1024 * 1024

let pollTimer = null

const fileLabel = computed(() => file.value ? file.value.name : '选择 PDF')
const canSubmit = computed(() => file.value && !isProcessing.value)
const fileSizeLabel = computed(() => {
  if (!file.value) return ''
  const size = file.value.size
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
})
const isLargeFile = computed(() => file.value && file.value.size > largeFileThreshold)
const overallProgress = computed(() => {
  if (!isProcessing.value && !downloadUrl.value) return 0
  return Math.min(100, Math.round(uploadProgress.value * 0.35 + jobProgress.value * 0.65))
})
const statusLabel = computed(() => {
  if (error.value) return '失败'
  if (downloadUrl.value) return '完成'
  if (isProcessing.value) return '处理中'
  if (file.value) return '已选择'
  return '待上传'
})
const statusIcon = computed(() => {
  if (error.value) return AlertTriangle
  if (downloadUrl.value) return CheckCircle2
  if (isProcessing.value) return LoaderCircle
  return Activity
})
const stages = computed(() => [
  { label: '上传', value: uploadProgress.value, active: isProcessing.value || uploadProgress.value > 0 },
  { label: '分析', value: jobProgress.value, active: jobProgress.value >= 25 },
  { label: '书签', value: jobProgress.value, active: jobProgress.value >= 80 },
  { label: '完成', value: downloadUrl.value ? 100 : 0, active: Boolean(downloadUrl.value) },
])

function resetResult() {
  report.value = ''
  error.value = ''
  uploadProgress.value = 0
  jobProgress.value = 0
  jobStep.value = ''
  jobId.value = ''
  downloadUrl.value = ''
  stopPolling()
}

function resetAll() {
  file.value = null
  maxPages.value = 50
  resetResult()
}

function onFileChange(event) {
  const selected = event.target.files?.[0]
  file.value = selected || null
  resetResult()
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function uploadJob(form) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/jobs')
    xhr.responseType = 'json'

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        uploadProgress.value = Math.round((event.loaded / event.total) * 100)
      }
    }

    xhr.onload = () => {
      const data = xhr.response || {}
      if (xhr.status >= 200 && xhr.status < 300) {
        uploadProgress.value = 100
        resolve(data)
      } else {
        reject(new Error(data.error || '上传失败，请稍后再试。'))
      }
    }

    xhr.onerror = () => reject(new Error('网络连接失败，请检查服务器是否正常运行。'))
    xhr.send(form)
  })
}

async function pollJobStatus(id) {
  const response = await fetch(`/api/jobs/${id}`)
  const data = await response.json()
  if (!response.ok) {
    throw new Error(data.error || '无法查询任务状态。')
  }

  jobStep.value = data.step || '处理中'
  jobProgress.value = data.progress || 0

  if (data.status === 'finished') {
    report.value = data.report || ''
    downloadUrl.value = data.download_url
    jobProgress.value = 100
    isProcessing.value = false
    stopPolling()
  } else if (data.status === 'failed') {
    throw new Error(data.error || '处理失败，请查看服务器日志。')
  }
}

function startPolling(id) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      await pollJobStatus(id)
    } catch (err) {
      error.value = err.message || '处理失败，请稍后再试。'
      isProcessing.value = false
      stopPolling()
    }
  }, 2000)
}

async function processPdf() {
  if (!file.value) {
    error.value = '请先选择一个 PDF 文件。'
    return
  }

  resetResult()
  isProcessing.value = true
  jobStep.value = '正在上传 PDF'

  const form = new FormData()
  form.append('pdf', file.value)
  form.append('max_pages', String(maxPages.value))

  try {
    const data = await uploadJob(form)
    jobId.value = data.job_id
    jobStep.value = data.step || '已上传，等待后台处理'
    jobProgress.value = data.progress || 10
    startPolling(data.job_id)
    await pollJobStatus(data.job_id)
  } catch (err) {
    error.value = err.message || '处理失败，请稍后再试。'
    isProcessing.value = false
    stopPolling()
  }
}

onBeforeUnmount(stopPolling)
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">
          <FileText :size="22" stroke-width="2.2" />
        </div>
        <div>
          <p class="product-name">PDF 目录工作台</p>
          <p class="product-subtitle">自动生成可点击书签</p>
        </div>
      </div>
      <div class="status-pill" :class="{ spinning: isProcessing }">
        <component :is="statusIcon" :size="16" />
        <span>{{ statusLabel }}</span>
      </div>
    </header>

    <section class="workspace">
      <aside class="side-rail" aria-label="处理阶段">
        <div v-for="stage in stages" :key="stage.label" class="stage" :class="{ active: stage.active }">
          <span class="stage-dot"></span>
          <span>{{ stage.label }}</span>
        </div>
      </aside>

      <section class="panel setup-panel">
        <div class="panel-heading">
          <div>
            <p class="section-kicker">Input</p>
            <h1>选择文件</h1>
          </div>
          <button class="icon-button" type="button" title="重置" @click="resetAll">
            <RotateCcw :size="18" />
          </button>
        </div>

        <form class="control-stack" @submit.prevent="processPdf">
          <label class="dropzone" :class="{ selected: file }">
            <input type="file" accept="application/pdf,.pdf" @change="onFileChange" />
            <span class="drop-icon">
              <FileUp :size="28" />
            </span>
            <span class="file-name">{{ fileLabel }}</span>
            <span class="file-meta">{{ file ? fileSizeLabel : 'PDF 文件' }}</span>
          </label>

          <div v-if="isLargeFile" class="callout">
            <AlertTriangle :size="18" />
            <span>文件较大，建议将分析页数设为 5-10 页。</span>
          </div>

          <div class="setting-row">
            <div class="setting-label">
              <Settings2 :size="18" />
              <span>分析页数</span>
            </div>
            <output>{{ maxPages }} 页</output>
          </div>
          <input v-model.number="maxPages" class="range" type="range" min="5" max="100" step="5" />

          <button class="primary-button" type="submit" :disabled="!canSubmit">
            <LoaderCircle v-if="isProcessing" :size="18" class="spin" />
            <FileUp v-else :size="18" />
            <span>{{ isProcessing ? '任务运行中' : '开始处理' }}</span>
          </button>
        </form>
      </section>

      <section class="panel result-panel" aria-live="polite">
        <div class="panel-heading compact">
          <div>
            <p class="section-kicker">Output</p>
            <h2>处理状态</h2>
          </div>
          <strong class="percent">{{ overallProgress }}%</strong>
        </div>

        <div class="progress-track" role="progressbar" :aria-valuenow="overallProgress" aria-valuemin="0" aria-valuemax="100">
          <div class="progress-fill" :style="{ width: `${overallProgress}%` }"></div>
        </div>

        <div class="status-line">
          <Activity :size="18" />
          <span>{{ jobStep || '等待文件' }}</span>
        </div>

        <p v-if="error" class="message error">
          <AlertTriangle :size="18" />
          <span>{{ error }}</span>
        </p>

        <div v-if="report" class="report-wrap">
          <pre class="report">{{ report }}</pre>
        </div>

        <div v-if="!report && !error" class="empty-state">
          <FileText :size="40" />
          <p>{{ isProcessing ? '后台任务正在执行' : '处理报告会显示在这里' }}</p>
        </div>

        <a v-if="downloadUrl" class="download-button" :href="downloadUrl">
          <Download :size="18" />
          <span>下载 PDF</span>
        </a>
      </section>
    </section>
  </main>
</template>
