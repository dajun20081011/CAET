<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const email = ref('')
const password = ref('')
const errorMsg = ref('')
const loading = ref(false)

async function handleLogin() {
  errorMsg.value = ''
  loading.value = true
  const { success, error } = await authStore.login(email.value, password.value)
  loading.value = false
  if (!success) {
    errorMsg.value = error || '登录失败'
    return
  }
  await authStore.initSession()
  if (authStore.isAdmin) {
    router.push('/admin/dashboard')
  } else {
    router.push('/student/tasks')
  }
}
</script>

<template>
  <div class="min-h-screen bg-background flex flex-col items-center justify-center p-6">
    <div class="w-full max-w-[360px]">
      <div class="text-center mb-10">
        <div class="w-16 h-16 rounded-2xl bg-primary flex items-center justify-center text-white font-bold text-2xl mx-auto mb-4 shadow-lg shadow-primary/30">
          C
        </div>
        <h1 class="text-2xl font-bold text-text mb-1">CAET 学练测</h1>
        <p class="text-sm text-text-secondary">Cabin Attendant English Training</p>
      </div>

      <div class="bg-white rounded-2xl p-6 shadow-sm">
        <h2 class="text-lg font-semibold text-text mb-4">账号登录</h2>

        <div v-if="errorMsg" class="mb-4 p-3 rounded-lg bg-red-50 text-danger text-sm">
          {{ errorMsg }}
        </div>

        <div class="space-y-4">
          <div>
            <label class="block text-sm text-text-secondary mb-1">邮箱</label>
            <input
              v-model="email"
              type="email"
              class="w-full px-4 py-3 rounded-lg border border-gray-200 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all text-sm"
              placeholder="请输入邮箱"
            />
          </div>
          <div>
            <label class="block text-sm text-text-secondary mb-1">密码</label>
            <input
              v-model="password"
              type="password"
              class="w-full px-4 py-3 rounded-lg border border-gray-200 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all text-sm"
              placeholder="请输入密码"
            />
          </div>

          <button
            @click="handleLogin"
            :disabled="loading || !email || !password"
            class="w-full btn-primary rounded-xl py-3.5 text-sm font-semibold mt-2"
          >
            {{ loading ? '登录中...' : '登录' }}
          </button>
        </div>
      </div>

      <p class="text-xs text-text-secondary text-center mt-6">
        Focus today. Shine tomorrow.
      </p>
    </div>
  </div>
</template>
