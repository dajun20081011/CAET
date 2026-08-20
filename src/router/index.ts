import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      redirect: '/login',
    },
    // Student routes（学员端：Tailwind 移动优先）
    {
      path: '/student',
      component: () => import('@/layouts/StudentLayout.vue'),
      meta: { requiresAuth: true, role: 'learner' },
      children: [
        { path: '', redirect: '/student/tasks' },
        { path: 'tasks', name: 'StudentTasks', component: () => import('@/views/student/StudentTasks.vue') },
        { path: 'tasks/:taskId', name: 'TaskDetail', component: () => import('@/views/student/TaskDetail.vue') },
        { path: 'course/:courseId/chapter/:chapter', name: 'ChapterView', component: () => import('@/views/student/ChapterView.vue') },
        { path: 'course/:courseId/chapter/:chapter/day/:day', name: 'DayStudy', component: () => import('@/views/student/DayStudy.vue') },
        { path: 'course/:courseId/chapter/:chapter/day/:day/weekly-test', name: 'WeeklyTest', component: () => import('@/views/student/WeeklyTest.vue') },
        { path: 'record', name: 'LearningRecord', component: () => import('@/views/student/LearningRecord.vue') },
        { path: 'assessments', name: 'StudentAssessments', component: () => import('@/views/student/StudentAssessments.vue') },
      ],
    },
    // Instructor routes（教员端：混合方案）
    {
      path: '/instructor',
      component: () => import('@/layouts/InstructorLayout.vue'),
      meta: { requiresAuth: true, role: 'instructor' },
      children: [
        { path: '', redirect: '/instructor/queue' },
        { path: 'queue', name: 'InstructorQueue', component: () => import('@/views/instructor/InstructorQueue.vue') },
        { path: 'assessments/:id', name: 'AssessmentGrade', component: () => import('@/views/instructor/AssessmentGrade.vue') },
      ],
    },
    // Admin routes（管理后台：Element Plus）
    {
      path: '/admin',
      component: () => import('@/layouts/AdminLayout.vue'),
      meta: { requiresAuth: true, role: 'admin' },
      children: [
        { path: '', redirect: '/admin/dashboard' },
        { path: 'dashboard', name: 'AdminDashboard', component: () => import('@/views/admin/AdminDashboard.vue') },
        { path: 'tasks', name: 'AdminTasks', component: () => import('@/views/admin/AdminTasks.vue') },
        { path: 'tasks/new', name: 'CreateTask', component: () => import('@/views/admin/CreateTask.vue') },
        { path: 'learners', name: 'AdminLearners', component: () => import('@/views/admin/AdminLearners.vue') },
        { path: 'learners/:learnerId', name: 'LearnerDetail', component: () => import('@/views/admin/LearnerDetail.vue') },
        { path: 'users', name: 'AdminUsers', component: () => import('@/views/admin/AdminUsers.vue') },
        { path: 'groups', name: 'AdminGroups', component: () => import('@/views/admin/AdminGroups.vue') },
        { path: 'assessments', name: 'AdminAssessments', component: () => import('@/views/admin/AdminAssessments.vue') },
        { path: 'events', name: 'AdminEvents', component: () => import('@/views/admin/AdminEvents.vue') },
      ],
    },
  ],
})

router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()
  await authStore.initSession()

  if (to.meta.public) {
    next()
    return
  }

  if (!authStore.isAuthenticated) {
    next('/login')
    return
  }

  if (to.meta.role && authStore.userRole !== to.meta.role) {
    const r = authStore.userRole
    if (r === 'admin') next('/admin')
    else if (r === 'instructor') next('/instructor')
    else next('/student')
    return
  }

  next()
})

export default router
