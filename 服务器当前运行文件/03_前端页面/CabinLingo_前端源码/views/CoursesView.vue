<template>
  <main class="app-shell page-shell course-page">
    <div class="course-page__top" aria-hidden="true">
      <span class="course-page__orb" />
      <img :src="studentArtwork" alt="" class="course-page__student">
      <span class="course-page__ring" />
    </div>

    <PageState v-if="loading" tone="loading" title="正在载入课程" />
    <PageState
      v-else-if="errorMessage"
      tone="error"
      title="课程载入失败"
      :message="errorMessage"
      action-label="重试"
      @action="loadCourses"
    />
    <template v-else>
      <header class="course-heading">
        <h1>课程</h1>
        <p>探索你的专属学习路径</p>
      </header>

      <label class="course-search">
        <span aria-hidden="true">⌕</span>
        <input v-model.trim="searchQuery" type="search" placeholder="搜索广播词、表达技巧" aria-label="搜索课程">
        <button v-if="searchQuery" type="button" aria-label="清除搜索" @click="searchQuery = ''">×</button>
      </label>

      <section v-if="heroCourse" class="continue-section" aria-labelledby="continue-heading">
        <h2 id="continue-heading">继续学习</h2>
        <button class="continue-course" type="button" @click="openCourse(heroCourse)">
          <span class="continue-course__cover"><img :src="bookArtwork" alt=""></span>
          <span class="continue-course__copy">
            <strong>{{ heroCourse.title }}</strong>
            <small>上次学习到 {{ lastPosition(heroCourse) }}</small>
            <span class="continue-course__track" aria-label="学习进度"><i :style="{ width: `${heroCourse.progress}%` }" /></span>
          </span>
          <img class="continue-course__play" :src="playArtwork" alt="继续学习">
        </button>
      </section>

      <section class="course-system" aria-labelledby="system-heading">
        <header class="course-system__heading">
          <h2 id="system-heading">课程体系</h2>
          <p>系统学习 · 持续提升</p>
        </header>

        <div class="course-categories" aria-label="课程分类">
          <button
            class="category-card category-card--expression"
            :class="{ 'is-selected': activeKind === 'expression_skill' }"
            type="button"
            @click="selectKind('expression_skill')"
          >
            <img class="category-card__cover" :src="expressionArtwork" alt="">
            <strong>表达技巧</strong>
            <small>{{ categoryCount('expression_skill') }} 门课程</small>
            <img class="category-card__arrow" :src="arrowArtwork" alt="">
          </button>
          <button
            class="category-card category-card--lesson"
            :class="{ 'is-selected': activeKind === 'lesson' }"
            type="button"
            @click="selectKind('lesson')"
          >
            <img class="category-card__cover" :src="lessonArtwork" alt="">
            <strong>课程讲解</strong>
            <small>{{ categoryCount('lesson') }} 门课程</small>
            <img class="category-card__arrow" :src="arrowArtwork" alt="">
          </button>
        </div>

        <section v-if="searchQuery || categoryExpanded" class="course-results" aria-live="polite" aria-label="课程列表">
          <header class="course-results__heading">
            <h3>{{ searchQuery ? '搜索结果' : activeKind === 'lesson' ? '课程讲解' : '表达技巧' }}</h3>
            <span>{{ filteredCourses.length }} 门</span>
          </header>
          <div v-if="filteredCourses.length" class="course-results__list">
            <button v-for="(course, index) in filteredCourses" :key="course.key" type="button" @click="openCourse(course)">
              <span class="course-index">{{ String(index + 1).padStart(2, '0') }}</span>
              <span class="course-results__copy">
                <strong>{{ course.title }}</strong>
                <small>{{ course.languageLabel }} · {{ course.progress >= 100 ? '已完成' : course.progress > 0 ? '学习中' : '待学习' }}</small>
              </span>
              <img :src="chevronGray" alt="">
            </button>
          </div>
          <p v-else class="course-results__empty">没有找到匹配课程</p>
        </section>
      </section>
    </template>
    <BottomNav />
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BottomNav from '@/components/BottomNav.vue'
import PageState from '@/components/PageState.vue'
import chevronGray from '@/assets/figma/course-chevron-gray.svg'
import studentArtwork from '@/assets/figma/course-hub/aff68.png'
import playArtwork from '@/assets/figma/course-hub/3c62e.png'
import bookArtwork from '@/assets/figma/course-hub/dccdb.png'
import expressionArtwork from '@/assets/figma/course-hub/a10da.png'
import lessonArtwork from '@/assets/figma/course-hub/5fc2f.png'
import arrowArtwork from '@/assets/figma/course-hub/db29b.png'
import { cabinlingoApi, type CourseV23Detail, type LearnerTask } from '@/api'
import { learnerError } from '@/domain/learnerPresentation'
import { useSessionStore } from '@/stores/session'

type CourseKind = 'lesson' | 'expression_skill'
interface LearnerCourse {
  key: string
  courseVersionId: string | null
  title: string
  languageLabel: string
  kind: CourseKind
  tasks: LearnerTask[]
  progress: number
  lastTask: LearnerTask | null
}

const router = useRouter()
const route = useRoute()
const session = useSessionStore()
const tasks = ref<LearnerTask[]>([])
const catalog = ref<CourseV23Detail[]>([])
const loading = ref(true)
const errorMessage = ref('')
const searchQuery = ref('')
const categoryExpanded = ref(Boolean(route.query.kind))
const activeKind = ref<CourseKind>(route.query.kind === 'expression_skill' ? 'expression_skill' : 'lesson')

const courses = computed<LearnerCourse[]>(() => {
  const grouped = new Map<string, LearnerTask[]>()
  tasks.value.forEach((task) => {
    const key = task.course_version_id || task.course_title
    grouped.set(key, [...(grouped.get(key) || []), task])
  })
  return catalog.value.map((item) => {
    const rows = grouped.get(item.course_version_id) || []
    const total = rows.reduce((sum, row) => sum + row.total_items, 0)
    const done = rows.reduce((sum, row) => sum + row.completed_items, 0)
    const languageLabel = item.language === 'zh' ? '中文' : item.language === 'en' ? 'English' : '中文 / English'
    const lastTask = rows.find(row => row.status !== 'completed' && !row.locked) || rows[0] || null
    return {
      key: item.course_version_id,
      courseVersionId: item.course_version_id,
      title: item.title_zh,
      languageLabel,
      kind: item.course_kind,
      tasks: rows,
      progress: total ? Math.round(done / total * 100) : 0,
      lastTask,
    }
  })
})
const visibleCourses = computed(() => courses.value.filter(course => course.kind === activeKind.value))
const heroCourse = computed(() => visibleCourses.value.find(course => course.progress > 0 && course.progress < 100) || visibleCourses.value[0] || null)
const filteredCourses = computed(() => visibleCourses.value
  .filter(course => !searchQuery.value || course.title.toLocaleLowerCase().includes(searchQuery.value.toLocaleLowerCase())))

function categoryCount(kind: CourseKind) {
  return courses.value.filter(course => course.kind === kind).length
}

function lastPosition(course: LearnerCourse) {
  try {
    const key = `cabinlingo.course-progress.v1:${session.user?.id || 'learner'}:${course.key}`
    const saved = JSON.parse(localStorage.getItem(key) || '{}') as { audio?: Record<string, { currentTime?: number }>; videoTime?: number }
    const savedAudio = Object.values(saved.audio || {}).reduce((latest, track) => Math.max(latest, Number(track.currentTime) || 0), 0)
    const position = Math.max(savedAudio, Number(saved.videoTime) || 0)
    if (position > 0) return `${String(Math.floor(position / 60)).padStart(2, '0')}:${String(Math.floor(position % 60)).padStart(2, '0')}`
  } catch { /* Browser storage can be disabled. */ }
  return course.lastTask?.completed_items ? '继续上次课程' : '尚未开始'
}

function openCourse(course: LearnerCourse | null) {
  if (!course) return
  const id = course.courseVersionId || course.tasks[0]?.course_version_id
  if (id) {
    void router.push(`/student/courses/${id}`)
    return
  }
  const task = course.tasks.find(item => !item.locked)
  if (task) void router.push(`/student/tasks/${task.assignment_id}`)
}

function selectKind(kind: CourseKind) {
  activeKind.value = kind
  categoryExpanded.value = true
  void router.replace({ path: route.path, query: { ...route.query, kind } })
}

async function loadCourses() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [published, rows] = await Promise.all([cabinlingoApi.learnerCourseV23Catalog(), cabinlingoApi.learnerTasks()])
    catalog.value = published
    tasks.value = rows.filter(task => task.status !== 'deleted')
  } catch (error) {
    errorMessage.value = learnerError(error)
  } finally {
    loading.value = false
  }
}

onMounted(loadCourses)
</script>

<style scoped>
.course-page{position:relative;width:100%;max-width:390px;min-height:844px;margin:0 auto;padding:44px 20px 112px;background:#f6faff;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;overflow-x:hidden;isolation:isolate}
.course-page__top{position:absolute;z-index:-1;left:0;right:0;top:0;height:240px;overflow:hidden;background:#eaf5ff;pointer-events:none}
.course-page__orb{position:absolute;right:-48px;top:-61px;width:190px;height:190px;border-radius:95px;background:#d5e9ff}
.course-page__student{position:absolute;right:37px;top:24px;width:105px;height:105px;object-fit:contain;animation:course-float 5s ease-in-out infinite}
.course-page__ring{position:absolute;right:-14px;top:78px;width:86px;height:86px;border-radius:50%;background:#ddefff}
.course-heading{position:relative;z-index:1}
.course-heading h1{margin:0;color:#112f5d;font-size:29px;line-height:36px;font-weight:750;letter-spacing:-.4px}
.course-heading p{margin:4px 0 0;color:#6c85a4;font-size:13px;line-height:20px}
.course-search{position:relative;z-index:1;display:flex;align-items:center;gap:9px;width:100%;height:48px;margin-top:19px;padding:0 15px;border-radius:16px;background:#fff;box-shadow:0 8px 20px #3e6da20c}
.course-search>span{color:#7992b1;font-size:28px;line-height:1;transform:rotate(-15deg)}
.course-search input{flex:1;min-width:0;border:0;outline:0;color:#183a70;background:transparent;font-size:14px}
.course-search input::placeholder{color:#8aa1bd;opacity:1}
.course-search input::-webkit-search-cancel-button{display:none}
.course-search button{width:25px;height:25px;border-radius:50%;color:#7992b1;background:#eff5fc;font-size:19px}
.continue-section{position:relative;margin-top:28px}
.continue-section h2,.course-system__heading h2{margin:0;color:#122f59;font-size:20px;line-height:26px;font-weight:700}
.continue-course{position:relative;display:block;width:100%;height:128px;margin-top:12px;padding:0;border-radius:20px;background:#fff;text-align:left;overflow:hidden;box-shadow:0 7px 20px #3763990b;transition:transform .2s ease,box-shadow .2s ease}
.continue-course__cover{position:absolute;left:9px;top:6px;display:grid;place-items:center;width:114px;height:114px;border-radius:14px;background:#d7ecff;overflow:hidden}
.continue-course__cover img{width:112px;height:112px;max-width:none;object-fit:contain}
.continue-course__copy{position:absolute;left:134px;right:28px;top:31px;z-index:1}
.continue-course__copy strong,.continue-course__copy small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.continue-course__copy strong{color:#183a70;font-size:17px;line-height:23px;font-weight:700}
.continue-course__copy small{margin-top:3px;color:#7992b1;font-size:12px;line-height:18px}
.continue-course__track{display:block;width:100%;height:5px;margin-top:11px;border-radius:3px;background:#e4eefb;overflow:hidden}
.continue-course__track i{display:block;height:100%;min-width:0;max-width:100%;border-radius:inherit;background:#2580ee;transition:width .25s ease}
.continue-course__play{position:absolute;right:8px;top:8px;width:88px;height:88px;max-width:none;object-fit:contain;opacity:.9}
.course-system{margin-top:37px}
.course-system__heading p{margin:2px 0 0;color:#7790b0;font-size:12px;line-height:18px}
.course-categories{display:grid;gap:12px;margin-top:13px}
.category-card{position:relative;width:100%;height:115px;border-radius:20px;text-align:left;overflow:hidden;transition:transform .2s ease,box-shadow .2s ease,filter .2s ease}
.category-card--expression{background:#e5f1ff}
.category-card--lesson{background:#e9f6f9}
.category-card.is-selected{box-shadow:inset 0 0 0 2px #72adef}
.category-card__cover{position:absolute;left:10px;top:10px;width:163px;height:95px;border-radius:15px;object-fit:cover;box-shadow:0 5px 15px #244e7721}
.category-card>strong{position:absolute;left:53%;right:12px;top:31px;color:#143967;font-size:19px;line-height:25px;font-weight:700;white-space:nowrap}
.category-card>small{position:absolute;left:53%;top:61px;color:#6684a7;font-size:11px;line-height:16px}
.category-card__arrow{position:absolute;right:-2px;top:-1px;width:41px;height:41px;max-width:none;object-fit:contain}
.course-results{margin-top:20px;animation:course-enter .24s ease-out both}
.course-results__heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.course-results__heading h3{margin:0;color:#122f59;font-size:17px;line-height:24px}
.course-results__heading span{color:#7790b0;font-size:12px}
.course-results__list{border-radius:16px;background:#fff;overflow:hidden}
.course-results__list button{display:flex;align-items:center;gap:12px;position:relative;width:100%;min-height:66px;padding:10px 15px;background:#fff;text-align:left;transition:background .18s ease}
.course-results__list button+button:before{content:"";position:absolute;top:0;left:58px;right:14px;height:1px;background:#e7eef7}
.course-index{display:grid;place-items:center;flex:none;width:32px;height:32px;border-radius:10px;color:#1463f2;background:#f1f6ff;font-size:11px;font-weight:600}
.course-results__copy{flex:1;min-width:0}
.course-results__copy strong,.course-results__copy small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.course-results__copy strong{color:#183a70;font-size:14px;line-height:20px;font-weight:600}
.course-results__copy small{margin-top:2px;color:#7992b1;font-size:11px;line-height:16px}
.course-results__list button>img{width:9px;height:14px;max-width:none}
.course-results__empty{margin:0;padding:24px;border-radius:16px;color:#7992b1;background:#fff;text-align:center;font-size:13px}
.course-page :deep(.page-state){position:relative;margin-top:80px}
@media(min-width:700px){.course-page{max-width:834px;min-height:100vh;padding:44px 40px 132px}.course-page__top{height:280px}.course-page__student{right:110px;width:145px;height:145px}.course-heading h1{font-size:32px}.course-search{max-width:754px}.continue-section,.course-system{max-width:754px}.course-categories{grid-template-columns:1fr 1fr;gap:14px}.category-card__cover{width:44%;}.category-card>strong,.category-card>small{left:50%}.course-results__list{display:grid;grid-template-columns:1fr 1fr}.course-results__list button:nth-child(even):after{content:"";position:absolute;left:0;top:10px;bottom:10px;width:1px;background:#e7eef7}}
@media(max-width:360px){.course-page{padding-inline:16px}.category-card__cover{width:45%}.category-card>strong,.category-card>small{left:52%}.category-card>strong{font-size:17px}.continue-course__cover{width:100px;height:100px;top:14px}.continue-course__cover img{width:98px;height:98px}.continue-course__copy{left:116px;right:22px}.continue-course__play{width:70px;height:70px}}
.continue-course:active,.category-card:active{transform:scale(.99)}
@keyframes course-enter{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:translateY(0)}}
@keyframes course-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
@media(prefers-reduced-motion:reduce){.course-page *{animation-duration:.01ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important;transition-duration:.01ms!important}}
</style>
