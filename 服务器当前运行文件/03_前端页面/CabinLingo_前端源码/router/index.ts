import { createRouter, createWebHashHistory } from 'vue-router'
import { useSessionStore } from '@/stores/session'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/student/home' },
    { path: '/login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    { path: '/auth-recovery', component: () => import('@/views/AuthRecoveryView.vue'), meta: { public: true } },
    { path: '/student/home', component: () => import('@/views/StudentHomeView.vue'), meta: { roles: ['learner'] } },
    { path: '/student/courses', component: () => import('@/views/CoursesView.vue'), meta: { roles: ['learner'] } },
    { path: '/student/courses/:courseId', component: () => import('@/views/CourseDetailView.vue'), meta: { roles: ['learner'] } },
    { path: '/student/tasks', component: () => import('@/views/TasksView.vue'), meta: { roles: ['learner'] } },
    { path: '/student/tasks/:assignmentId', component: () => import('@/views/TaskDetailView.vue'), meta: { roles: ['learner'] } },
    { path: '/student/practice', component: () => import('@/views/PracticeView.vue'), meta: { roles: ['learner'] } },
    { path: '/student/exam', component: () => import('@/views/ExamView.vue'), meta: { roles: ['learner'] } },
    {
      path: '/student/record',
      redirect: (to) => {
        const tab = typeof to.query.tab === 'string' ? to.query.tab : ''
        const path = tab === 'feedback' ? '/student/feedback' : tab === 'growth' ? '/student/growth' : '/student/results'
        return { path, query: to.query }
      },
    },
    { path: '/student/results', component: () => import('@/views/RecordView.vue'), meta: { roles: ['learner'], recordTab: 'attempts' } },
    { path: '/student/results/week/:assignmentId', component: () => import('@/views/AssessmentWeekView.vue'), meta: { roles: ['learner'] } },
    { path: '/student/results/:attemptId', component: () => import('@/views/ResultDetailView.vue'), meta: { roles: ['learner'] } },
    { path: '/student/results/:attemptId/coach', component: () => import('@/views/PronunciationCoachView.vue'), meta: { roles: ['learner'] } },
    { path: '/student/results/:attemptId/coach/:wordIndex', component: () => import('@/views/PronunciationCoachView.vue'), meta: { roles: ['learner'] } },
    { path: '/student/feedback', component: () => import('@/views/RecordView.vue'), meta: { roles: ['learner'], recordTab: 'feedback' } },
    { path: '/student/growth', component: () => import('@/views/RecordView.vue'), meta: { roles: ['learner'], recordTab: 'growth' } },
    { path: '/student/profile', component: () => import('@/views/ProfileView.vue'), meta: { roles: ['learner'] } },
    { path: '/evaluator', redirect: '/instructor/home' },
    { path: '/instructor', redirect: '/instructor/home' },
    { path: '/instructor/workbench', redirect: '/instructor/evaluations' },
    { path: '/instructor/reviews', redirect: '/instructor/evaluations' },
    { path: '/instructor/analytics', redirect: '/instructor/profile' },
    { path: '/instructor/classes', redirect: '/instructor/profile' },
    { path: '/instructor/:section(home|evaluations|students|profile)', component: () => import('@/views/EvaluatorView.vue'), meta: { roles: ['evaluator', 'instructor', 'admin'] } },
    { path: '/admin', redirect: '/admin/dashboard' },
    { path: '/admin/mobile', redirect: '/admin/mobile/home' },
    { path: '/admin/mobile/:view(home|completed|pending|incomplete|weekly|learners)', name: 'admin-mobile', component: () => import('@/views/AdminMobileV2View.vue'), meta: { roles: ['admin'] } },
    { path: '/admin/mobile/learner/:learnerId', name: 'admin-mobile-learner', component: () => import('@/views/AdminMobileV2View.vue'), meta: { roles: ['admin'] } },
    { path: '/admin/mobile/learner/:learnerId/task/:taskId', name: 'admin-mobile-week', component: () => import('@/views/AdminMobileV2View.vue'), meta: { roles: ['admin'] } },
    { path: '/admin/mobile/learner/:learnerId/attempt/:attemptId', name: 'admin-mobile-attempt', component: () => import('@/views/AdminMobileV2View.vue'), meta: { roles: ['admin'] } },
    { path: '/admin/broadcast-scripts', component: () => import('@/views/BroadcastScriptsView.vue'), meta: { roles: ['admin'] } },
    { path: '/admin/:section(dashboard|organizations|users|courses|prosody|tasks|settings|permissions|ai|analytics)?', component: () => import('@/views/AdminEntryView.vue'), meta: { roles: ['admin'] } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const session = useSessionStore()
  if (to.path === '/auth-recovery') return true
  const hadToken = session.hasStoredToken()
  if (to.meta.public && !hadToken) return true
  let authenticated = session.hasCurrentSession()
  try {
    authenticated = authenticated || await session.restore()
  } catch {
    return { path: '/auth-recovery', query: { redirect: to.fullPath } }
  }
  if (!authenticated && session.hasStoredToken()) {
    return { path: '/auth-recovery', query: { redirect: to.fullPath } }
  }
  if (to.meta.public) {
    if (authenticated) return session.landingPage()
    return hadToken ? { path: '/login', query: { ...to.query, reason: 'expired' } } : true
  }
  if (!authenticated) return { path: '/login', query: { redirect: to.fullPath, ...(hadToken ? { reason: 'expired' } : {}) } }
  const roles = (to.meta.roles as string[] | undefined) || []
  if (roles.length && !roles.some((role) => session.hasRole(role))) return session.landingPage()
  return true
})

export default router
