<template>
  <main class="app-shell page-shell home-v3">
    <img class="home-v3__flow" :src="backgroundFlow" alt="">
    <img class="home-v3__accents" :src="heroAccents" alt="">
    <header class="home-v3__hero">
      <h1>你好，<br>一起<span>学习</span>吧</h1>
      <p>CabinLingo，让表达更出色！</p>
      <div class="home-v3__student-crop"><img :src="heroStudent" alt=""></div>
    </header>

    <div v-if="loading" class="home-v3__state" role="status">正在加载学习数据…</div>
    <div v-else-if="apiError" class="home-v3__state home-v3__state--error" role="alert">
      <span>{{ apiError }}</span><button type="button" @click="loadHome">重试</button>
    </div>

    <template v-else>
      <section class="home-v3__task" aria-labelledby="weekly-task-title">
        <div class="home-v3__section-title">
          <img :src="calendarIcon" alt="">
          <h2 id="weekly-task-title">本周学习任务</h2>
        </div>
        <h3>{{ weeklyTask?.title || '暂无学习任务' }}</h3>
        <div class="home-v3__progress">
          <div><strong>学习进度</strong><b>{{ submittedCount }}/{{ taskTotal }} 篇</b></div>
          <span><i :style="{ width: `${progressPercent}%` }" /></span>
        </div>
        <button type="button" :disabled="!weeklyTask || weeklyTask.locked" @click="openTask">
          {{ weeklyTask ? (submittedCount ? '继续学习' : '开始学习') : '暂无待完成任务' }}<span aria-hidden="true">›</span>
        </button>
      </section>

      <section class="home-v3__mistakes" aria-labelledby="mistake-title">
        <img class="home-v3__mistake-icon" :src="mistakeWordsIcon" alt="">
        <div><h2 id="mistake-title">我的易错词</h2><p>这些词你容易出错，多复习一下吧！</p></div>
        <RouterLink to="/student/growth">查看全部 ›</RouterLink>
        <ul><li v-for="word in displayedMistakeWords" :key="word">{{ word }}</li></ul>
      </section>

      <section class="home-v3__records" aria-labelledby="record-title">
        <div class="home-v3__record-icon" aria-hidden="true"><i /><i /><i /></div>
        <h2 id="record-title">学习记录</h2>
        <RouterLink to="/student/results">查看详情 ›</RouterLink>
        <dl>
          <div><dt>{{ studyDays }}</dt><dd>累计学习天数</dd></div>
          <div><dt>{{ submittedTotal }}</dt><dd>已提交篇目</dd></div>
          <div><dt>{{ todayMinutes }}</dt><dd>今日学习时长<span>分钟</span></dd></div>
        </dl>
      </section>
    </template>
    <BottomNav />
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import BottomNav from '@/components/BottomNav.vue'
import { cabinlingoApi, type LearnerAttempt, type LearnerHome, type LearnerTask } from '@/api'
import { learnerError } from '@/domain/learnerPresentation'
import backgroundFlow from '@/assets/home-v3/background-flow.svg'
import heroAccents from '@/assets/home-v3/hero-accents.svg'
import heroStudent from '@/assets/home-v3/hero-student.png'
import calendarIcon from '@/assets/home-v3/calendar.png'
import mistakeWordsIcon from '@/assets/home-v3/mistake-words.png'

const router = useRouter()
const apiError = ref('')
const loading = ref(true)
const attempts = ref<LearnerAttempt[]>([])
const tasks = ref<LearnerTask[]>([])
const home = reactive<LearnerHome>({ practice_count: 0, exam_count: 0, completed_count: 0, total_attempts: 0, pending_feedback: 0, next_task: null })

function completed(task: LearnerTask) { return task.status === 'completed' || Number(task.progress_percent) >= 100 }
function pending(task: LearnerTask) { return task.status !== 'deleted' && !completed(task) }
function taskTime(task: LearnerTask) { return task.due_at ? new Date(task.due_at).getTime() : Number.MAX_SAFE_INTEGER }

const weeklyTask = computed(() => {
  if (home.next_task?.task_type === 'practice' && pending(home.next_task)) return home.next_task
  return [...tasks.value].filter(task => task.task_type === 'practice' && pending(task)).sort((a, b) => taskTime(a) - taskTime(b))[0] || null
})
const successfulWeeklyAttempts = computed(() => attempts.value.filter(item => item.assignment_id === weeklyTask.value?.assignment_id && Boolean(item.recording_url)))
const submittedContentIds = computed(() => new Set(successfulWeeklyAttempts.value.map(item => item.content_item_id || item.attempt_id)))
const taskTotal = computed(() => Math.max(weeklyTask.value?.total_items || 0, 0))
const submittedCount = computed(() => Math.min(taskTotal.value, submittedContentIds.value.size))
const progressPercent = computed(() => taskTotal.value ? Math.min(100, Math.round(submittedCount.value / taskTotal.value * 100)) : 0)
const allSubmittedContentIds = computed(() => new Set(attempts.value.filter(item => item.recording_url).map(item => item.content_item_id || item.attempt_id)))
const submittedTotal = computed(() => allSubmittedContentIds.value.size)
const dateKey = (value: string | Date) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date(value))
const studyDays = computed(() => new Set(attempts.value.filter(item => item.recording_url).map(item => dateKey(item.created_at))).size)
const todayMinutes = computed(() => Math.round(attempts.value.filter(item => item.recording_url && dateKey(item.created_at) === dateKey(new Date())).reduce((sum, item) => sum + Number(item.duration_seconds || 0), 0) / 60))
const mistakeWords = computed(() => {
  const words = attempts.value.flatMap(item => item.issues || []).map(issue => String(issue.word || issue.expected || '').trim()).filter(Boolean)
  return [...new Set(words)].slice(0, 5)
})
const displayedMistakeWords = computed(() => mistakeWords.value.length ? mistakeWords.value : ['继续保持', '暂无易错词'])

function openTask() {
  const task = weeklyTask.value
  if (!task || task.locked) return
  void router.push({ path: `/student/tasks/${task.assignment_id}`, query: { task: task.task_id, content: task.next_content_item_id || undefined } })
}

async function loadHome() {
  loading.value = true
  apiError.value = ''
  try {
    const [homeData, taskRows, attemptRows] = await Promise.all([cabinlingoApi.learnerHome(), cabinlingoApi.learnerTasks(), cabinlingoApi.learnerAttempts()])
    Object.assign(home, homeData)
    tasks.value = taskRows.filter(task => task.status !== 'deleted')
    attempts.value = attemptRows
  } catch (error) {
    apiError.value = learnerError(error)
  } finally {
    loading.value = false
  }
}
onMounted(() => { void loadHome() })
</script>

<style scoped>
.home-v3{position:relative;width:100%;max-width:390px;min-height:844px;margin:0 auto;padding:0 16px;background:linear-gradient(180deg,#d1edff 0%,#e8f7ff 58%,#f6fbff 100%);font-family:"Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;overflow:hidden}
.home-v3__flow{position:absolute;left:0;top:40px;width:390px;height:300px;max-width:none}.home-v3__accents{position:absolute;left:142px;top:66px;width:232px;height:70px;max-width:none}
.home-v3__hero{position:relative;height:240px}.home-v3__hero h1{position:absolute;z-index:2;left:11px;top:84px;margin:0;color:#102b57;font-size:28px;line-height:1.42;font-weight:800;letter-spacing:-.7px}.home-v3__hero h1 span{color:#1479f8}.home-v3__hero p{position:absolute;z-index:2;left:0;top:176px;margin:0;color:#1d385b;font-size:15px;line-height:25px;font-weight:700}.home-v3__student-crop{position:absolute;z-index:1;left:145px;top:16px;width:210px;height:224px;overflow:hidden}.home-v3__student-crop img{position:absolute;left:-21px;top:1px;width:250px;height:270px;max-width:none;object-fit:contain}
.home-v3__state{position:absolute;z-index:5;left:16px;right:16px;top:240px;display:flex;align-items:center;justify-content:center;gap:12px;min-height:274px;padding:24px;border-radius:24px;background:#fff;color:#526581;box-shadow:0 8px 22px rgba(51,122,212,.1)}.home-v3__state--error{flex-direction:column;color:#b52d43;text-align:center}.home-v3__state button{min-width:90px;padding:10px 18px;border-radius:22px;color:#fff;background:#287cf4}
.home-v3__task{position:relative;height:274px;padding:16px 17px 23px;border-radius:24px;background:#fff;box-shadow:0 8px 22px rgba(51,122,212,.1)}.home-v3__section-title{display:flex;align-items:center;gap:16px;height:44px}.home-v3__section-title img{width:44px;height:44px;object-fit:contain}.home-v3__section-title h2{margin:0;color:#0b1b3e;font-size:17px;font-weight:800}.home-v3__task h3{height:46px;margin:0;padding:4px 14px 0;color:#1c3052;font-size:clamp(20px,7.7vw,32px);line-height:42px;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.home-v3__progress{height:69px;padding:8px 14px 0;border-radius:18px;background:linear-gradient(90deg,#f6faff,#eaf5ff)}.home-v3__progress>div{display:flex;align-items:center;justify-content:space-between}.home-v3__progress strong{color:#1d2944;font-size:15px}.home-v3__progress b{color:#2479f2;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:20px}.home-v3__progress>span{display:block;width:100%;height:10px;margin-top:6px;border-radius:6px;background:#dae4f0;overflow:hidden}.home-v3__progress i{display:block;height:100%;border-radius:6px;background:linear-gradient(90deg,#2c9bff,#2a7cf4);transition:width .32s cubic-bezier(.22,.8,.36,1)}
.home-v3__task>button{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;height:45px;min-height:45px;margin-top:20px;border-radius:23px;color:#fff;background:linear-gradient(90deg,#2c9cff,#287cf4);box-shadow:0 5px 12px rgba(31,122,242,.16);font-size:16px;font-weight:900;transition:transform .18s ease,filter .18s ease}.home-v3__task>button:not(:disabled):active{transform:scale(.98)}.home-v3__task>button:disabled{opacity:.6}
.home-v3__mistakes{position:relative;height:117px;margin-top:12px;padding:15px 14px;border-radius:22px;background:linear-gradient(90deg,#fff,#eefff5);box-shadow:0 6px 18px rgba(46,166,115,.08);overflow:hidden}.home-v3__mistake-icon{position:absolute;left:1px;top:2px;width:66px;height:66px;object-fit:cover}.home-v3__mistakes>div{margin-left:53px}.home-v3__mistakes h2{margin:0;color:#122443;font-size:17px;line-height:24px}.home-v3__mistakes p{margin:4px 0 0;color:#7c8aa0;font-size:11px;font-weight:700}.home-v3__mistakes>a{position:absolute;right:18px;top:18px;color:#687c9a;font-size:11px;text-decoration:none}.home-v3__mistakes ul{position:absolute;left:14px;right:8px;bottom:15px;display:flex;gap:4px;margin:0;padding:0;list-style:none}.home-v3__mistakes li{flex:1;min-width:0;height:29px;padding:7px;border-radius:15px;color:#173a36;background:linear-gradient(90deg,#f2fff7,#ddf8e8);font-family:Inter,sans-serif;font-size:10px;line-height:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.home-v3__records{position:relative;height:105px;margin-top:11px;border-radius:22px;background:#fff;box-shadow:0 6px 18px rgba(56,115,191,.08)}.home-v3__record-icon{position:absolute;left:17px;top:13px;display:flex;align-items:end;justify-content:center;gap:3px;width:30px;height:30px;padding:7px 6px;border-radius:8px;background:#efeaff}.home-v3__record-icon i{display:block;width:4px;border-radius:2px;background:#7357ff}.home-v3__record-icon i:nth-child(1){height:9px}.home-v3__record-icon i:nth-child(2){height:16px}.home-v3__record-icon i:nth-child(3){height:12px}.home-v3__records h2{position:absolute;left:61px;top:17px;margin:0;color:#132342;font-size:16px}.home-v3__records>a{position:absolute;right:21px;top:19px;color:#687c9a;font-size:11px;text-decoration:none}.home-v3__records dl{position:absolute;left:20px;right:20px;bottom:10px;display:grid;grid-template-columns:repeat(3,1fr);margin:0}.home-v3__records dl>div{text-align:center;border-right:1px solid #d9e4f1}.home-v3__records dl>div:last-child{border:0}.home-v3__records dt{color:#10254a;font-size:21px;line-height:24px;font-weight:800}.home-v3__records dd{margin:1px 0 0;color:#7b8da8;font-size:10px}.home-v3__records dd span{margin-left:4px;font-size:8px}
@media(min-width:700px){.home-v3{max-width:390px;min-height:844px;padding-left:16px;padding-right:16px}.learner-app .home-v3{max-width:390px}}
@media(prefers-reduced-motion:reduce){.home-v3__progress i,.home-v3__task>button{transition:none}}
</style>
