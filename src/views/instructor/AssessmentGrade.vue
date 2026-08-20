<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/lib/api'

const route = useRoute()
const router = useRouter()

const id = computed(() => Number(route.params.id))
const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const data = ref<any | null>(null)

const score = ref<number | null>(null)
const feedback = ref('')
const status = ref<'graded' | 'resubmit'>('graded')

// 上传 URL 前缀：/uploads/xxx
function absUrl(u: string | null | undefined): string | null {
  if (!u) return null
  if (u.startsWith('http')) return u
  return u
}

const typeLabel = computed(() => {
  const t = data.value?.assessment_type
  if (t === 'broadcast_recording') return '广播词录音'
  if (t === 'english_qa') return '英文问答'
  if (t === 'zh_to_en') return '中译英'
  return t || '—'
})

const answerItems = computed(() => {
  const a = data.value?.answers || {}
  return Object.entries(a)
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.assessments.get(id.value)
    score.value = data.value?.score ?? null
    feedback.value = data.value?.feedback || ''
    status.value = (data.value?.status === 'resubmit' ? 'resubmit' : 'graded') as any
  } catch (e: any) {
    error.value = e?.message || '加载失败'
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!data.value) return
  submitting.value = true
  try {
    await api.assessments.grade(id.value, {
      score: score.value,
      feedback: feedback.value || null,
      status: status.value,
    })
    ElMessage.success('评分已提交')
    router.push('/instructor/queue')
  } catch (e: any) {
    ElMessage.error(e?.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

function fmt(s: string | null) {
  if (!s) return '—'
  try { return new Date(s).toLocaleString('zh-CN', { hour12: false }) }
  catch { return s }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="space-y-5">
    <button @click="router.back()" class="text-sm text-text-secondary hover:text-text flex items-center gap-1">
      <el-icon><ArrowLeft /></el-icon>
      返回队列
    </button>

    <div v-if="data" class="space-y-5">
      <!-- Header -->
      <div class="rounded-xl bg-white border border-gray-100 p-5">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <p class="text-xs text-text-secondary">{{ typeLabel }} · 测评详情</p>
            <h2 class="text-xl font-bold text-text mt-1">
              {{ data.learner_name || '学员' }} ·
              <span class="text-text-secondary font-normal text-base">{{ data.task_title || '—' }}</span>
            </h2>
            <p class="text-xs text-text-secondary mt-1">课程：{{ data.course_title || '—' }} · 提交时间：{{ fmt(data.created_at) }}</p>
          </div>
          <el-tag v-if="data.status === 'graded'" type="success">已评分</el-tag>
          <el-tag v-else-if="data.status === 'resubmit'" type="warning">需重提交</el-tag>
          <el-tag v-else type="info">已提交</el-tag>
        </div>
      </div>

      <!-- Answers / Recordings -->
      <div class="rounded-xl bg-white border border-gray-100 p-5 space-y-4">
        <h3 class="text-sm font-semibold text-text">学员提交内容</h3>

        <!-- broadcast_recording: 两条录音 -->
        <template v-if="data.assessment_type === 'broadcast_recording'">
          <div class="space-y-3">
            <div>
              <p class="text-xs text-text-secondary mb-1">中文录音</p>
              <audio v-if="absUrl(data.answers?.cn_audio_url)" :src="absUrl(data.answers?.cn_audio_url)!" controls class="w-full" />
              <p v-else class="text-sm text-text-secondary">未提交</p>
            </div>
            <div>
              <p class="text-xs text-text-secondary mb-1">英文录音</p>
              <audio v-if="absUrl(data.answers?.en_audio_url)" :src="absUrl(data.answers?.en_audio_url)!" controls class="w-full" />
              <p v-else class="text-sm text-text-secondary">未提交</p>
            </div>
          </div>
        </template>

        <!-- english_qa / zh_to_en: 文本作答 -->
        <template v-else>
          <div class="space-y-3">
            <div v-for="[k, v] in answerItems" :key="k" class="rounded-lg bg-gray-50 p-3">
              <p class="text-xs text-text-secondary mb-1">{{ k }}</p>
              <p class="text-sm text-text whitespace-pre-wrap">{{ typeof v === 'string' ? v : JSON.stringify(v, null, 2) }}</p>
            </div>
            <p v-if="!answerItems.length" class="text-sm text-text-secondary">未提交文本作答</p>
          </div>
        </template>
      </div>

      <!-- Grading form -->
      <div class="rounded-xl bg-white border border-gray-100 p-5 space-y-4">
        <h3 class="text-sm font-semibold text-text">评分与反馈</h3>

        <div class="flex items-center gap-3">
          <span class="text-sm text-text-secondary w-16">分数</span>
          <el-input-number v-model="score" :min="0" :max="100" :step="1" placeholder="0-100" />
          <span class="text-xs text-text-secondary">分（0-100，可空）</span>
        </div>

        <div>
          <span class="text-sm text-text-secondary block mb-2">反馈</span>
          <el-input v-model="feedback" type="textarea" :rows="4" placeholder="对学员表现的反馈与改进建议" maxlength="500" show-word-limit />
        </div>

        <div class="flex items-center gap-4">
          <span class="text-sm text-text-secondary w-16">结果</span>
          <el-radio-group v-model="status">
            <el-radio-button value="graded">评分通过</el-radio-button>
            <el-radio-button value="resubmit">需重提交</el-radio-button>
          </el-radio-group>
        </div>

        <div class="flex justify-end gap-3 pt-2 border-t border-gray-100">
          <el-button @click="router.back()">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submit">提交评分</el-button>
        </div>
      </div>
    </div>

    <div v-else-if="error" class="text-sm text-danger">{{ error }}</div>
  </div>
</template>

<style scoped>
.bg-gray-50 { background-color: #F9FAFB; }
.bg-primary-soft { background-color: #F3EDFF; }
.text-primary { color: #7C3AED; }
.text-text { color: #1F2430; }
.text-text-secondary { color: #687280; }
.text-danger { color: #EF4444; }
.border-gray-100 { border-color: #F3F4F6; }
.hover\:text-text:hover { color: #1F2430; }
</style>