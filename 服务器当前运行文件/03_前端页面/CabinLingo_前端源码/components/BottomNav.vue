<template>
  <nav class="bottom-nav" aria-label="学员端主导航">
    <RouterLink
      v-for="item in items"
      :key="item.to"
      :to="item.to"
      class="bottom-nav__item"
      :class="{ 'is-active': isActive(item.to) }"
      :aria-current="isActive(item.to) ? 'page' : undefined"
    >
      <span class="bottom-nav__selection" aria-hidden="true" />
      <img class="bottom-nav__icon" :src="isActive(item.to) ? item.activeIcon : item.icon" alt="">
      <span class="bottom-nav__label">{{ item.label }}</span>
    </RouterLink>
  </nav>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import homeActive from '@/assets/home-v3/nav-home-active.svg'
import homeInactive from '@/assets/home-v3/nav-home-inactive.svg'
import courseActive from '@/assets/home-v3/nav-course-active.svg'
import courseInactive from '@/assets/home-v3/nav-course-inactive.svg'
import trainingActive from '@/assets/home-v3/nav-training-active.svg'
import trainingInactive from '@/assets/home-v3/nav-training-inactive.svg'
import feedbackActive from '@/assets/home-v3/nav-feedback-active.svg'
import feedbackInactive from '@/assets/home-v3/nav-feedback-inactive.svg'
import profileActive from '@/assets/home-v3/nav-profile-active.svg'
import profileInactive from '@/assets/home-v3/nav-profile-inactive.svg'

const route = useRoute()

const items = [
  { to: '/student/home', label: '首页', icon: homeInactive, activeIcon: homeActive },
  { to: '/student/courses', label: '课程', icon: courseInactive, activeIcon: courseActive },
  { to: '/student/tasks', label: '训练', icon: trainingInactive, activeIcon: trainingActive },
  { to: '/student/feedback', label: '反馈', icon: feedbackInactive, activeIcon: feedbackActive },
  { to: '/student/profile', label: '我的', icon: profileInactive, activeIcon: profileActive },
]

function isActive(to: string) {
  if (to === '/student/feedback') return ['/student/results', '/student/feedback', '/student/growth'].some(path => route.path === path || route.path.startsWith('/student/results/'))
  if (to === '/student/tasks') return route.path === '/student/tasks' || route.path.startsWith('/student/tasks/') || ['/student/practice', '/student/exam'].includes(route.path)
  if (to === '/student/courses') return route.path === '/student/courses' || route.path.startsWith('/student/courses/')
  return route.path === to
}
</script>
