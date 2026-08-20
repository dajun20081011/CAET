import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { api, getToken, setToken, clearToken, type ApiUser } from '@/lib/api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<ApiUser | null>(null)
  const session = ref<{ user: { id: string } } | null>(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => !!session.value)
  const userRole = computed(() => user.value?.role || null)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isLearner = computed(() => user.value?.role === 'learner')

  async function initSession() {
    if (!getToken()) {
      user.value = null
      session.value = null
      return
    }
    try {
      user.value = await api.auth.me()
      session.value = { user: { id: user.value.id } }
    } catch {
      // token 无效或已过期，清除登录态，路由守卫会跳登录页
      user.value = null
      session.value = null
    }
  }

  async function login(email: string, password: string) {
    loading.value = true
    try {
      const r = await api.auth.login(email, password)
      setToken(r.access_token)
      user.value = r.user
      session.value = { user: { id: r.user.id } }
      return { success: true }
    } catch (err: any) {
      return { success: false, error: err?.message || '登录失败' }
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try {
      await api.auth.logout()
    } catch {
      /* 忽略登出接口异常，本地清理即可 */
    }
    clearToken()
    user.value = null
    session.value = null
  }

  return {
    user,
    session,
    loading,
    isAuthenticated,
    userRole,
    isAdmin,
    isLearner,
    initSession,
    login,
    logout,
  }
})
