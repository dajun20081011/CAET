<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()

function logout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Desktop sidebar (Element Plus) -->
    <aside class="fixed left-0 top-0 h-full w-60 bg-white border-r border-gray-200 z-50 hidden md:block">
      <div class="p-5">
        <div class="flex items-center gap-2 mb-8">
          <div class="w-9 h-9 rounded-lg bg-primary flex items-center justify-center text-white font-bold">C</div>
          <span class="font-bold text-text">CAET 教员端</span>
        </div>
        <nav class="space-y-1">
          <router-link to="/instructor/queue" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
            :class="$route.path.includes('/queue') ? 'bg-primary-soft text-primary font-medium' : 'text-text-secondary hover:bg-gray-50'">
            <el-icon><BellFilled /></el-icon>
            <span>待评分队列</span>
          </router-link>
        </nav>
      </div>
      <div class="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-200">
        <button @click="logout" class="flex items-center gap-2 text-sm text-danger w-full px-3 py-2 rounded-lg hover:bg-red-50 transition-colors">
          <el-icon><SwitchButton /></el-icon>
          退出登录
        </button>
      </div>
    </aside>

    <!-- Main -->
    <main class="md:ml-60 min-h-screen">
      <header class="bg-white border-b border-gray-200 px-5 md:px-8 py-4 flex items-center justify-between">
        <h1 class="text-base md:text-lg font-semibold text-text">
          {{ $route.meta.title || '教员工作台' }}
        </h1>
        <div class="flex items-center gap-3">
          <span class="text-sm text-text-secondary hidden sm:inline">{{ authStore.user?.display_name || '教员' }}</span>
          <div class="w-9 h-9 rounded-full bg-primary-soft text-primary flex items-center justify-center text-sm font-medium">
            {{ (authStore.user?.display_name || 'T')[0] }}
          </div>
        </div>
      </header>
      <div class="p-5 md:p-8 max-w-[1200px] mx-auto">
        <router-view />
      </div>
    </main>
  </div>
</template>

<style scoped>
.bg-primary { background-color: #7C3AED; }
.bg-primary-soft { background-color: #F3EDFF; }
.text-primary { color: #7C3AED; }
.text-text { color: #1F2430; }
.text-text-secondary { color: #687280; }
.text-danger { color: #EF4444; }
.border-gray-200 { border-color: #E5E7EB; }
.border-gray-50 { border-color: #F9FAFB; }
.hover\:bg-red-50:hover { background-color: #FEF2F2; }
.hover\:bg-gray-50:hover { background-color: #F9FAFB; }
</style>