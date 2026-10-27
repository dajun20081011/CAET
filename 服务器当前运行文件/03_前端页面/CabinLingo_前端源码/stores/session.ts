import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { authErrorMessage, cabinlingoApi, clearAccessToken, isUnauthorizedError, readAccessToken, writeAccessToken, type CurrentUser } from '@/api'

export const useSessionStore = defineStore('session', () => {
  const user = ref<CurrentUser | null>(null)
  const restoring = ref(false)
  const restoreError = ref('')
  const userToken = ref('')
  let generation = 0
  let restoreRequest: Promise<boolean> | null = null
  let restoringToken = ''
  const isLoggedIn = computed(hasCurrentSession)
  const displayName = computed(() => user.value?.display_name || '')
  const cabinlingoRoles = computed(() => user.value?.memberships.find((item) => item.product === 'cabinlingo')?.roles || [])

  function hasRole(role: string): boolean {
    return cabinlingoRoles.value.includes(role)
  }

  function landingPage(): string {
    if (hasRole('admin')) return '/admin/dashboard'
    if (hasRole('instructor') || hasRole('evaluator')) return '/instructor/home'
    return '/student/home'
  }

  async function signIn(account: string, password: string, remember: boolean): Promise<void> {
    const response = await cabinlingoApi.login(account, password)
    writeAccessToken(response.access_token, remember)
    generation += 1
    userToken.value = response.access_token
    user.value = response.user
    restoreError.value = ''
  }

  async function restore(): Promise<boolean> {
    if (hasCurrentSession()) return true
    const token = readAccessToken()
    if (!token) return false
    if (restoreRequest && restoringToken === token) return restoreRequest
    const attempt = generation
    restoring.value = true
    restoringToken = token
    restoreError.value = ''
    const request = (async () => {
      try {
        const restoredUser = await cabinlingoApi.me()
        if (attempt !== generation || token !== readAccessToken()) return hasCurrentSession()
        user.value = restoredUser
        userToken.value = token
        return true
      } catch (error) {
        // Ignore results from before a logout, re-login or cross-tab token change.
        if (attempt !== generation || token !== readAccessToken()) return hasCurrentSession()
        if (isUnauthorizedError(error)) {
          signOut()
          return false
        }
        restoreError.value = authErrorMessage(error)
        throw error
      }
    })()
    restoreRequest = request
    try {
      return await request
    } finally {
      if (restoreRequest === request) {
        restoring.value = false
        restoreRequest = null
        restoringToken = ''
      }
    }
  }

  function signOut(): void {
    generation += 1
    restoreRequest = null
    restoringToken = ''
    restoring.value = false
    restoreError.value = ''
    userToken.value = ''
    user.value = null
    clearAccessToken()
  }

  function hasCurrentSession(): boolean {
    return Boolean(user.value && userToken.value && userToken.value === readAccessToken())
  }

  function hasStoredToken(): boolean {
    return Boolean(readAccessToken())
  }

  return { user, displayName, cabinlingoRoles, isLoggedIn, restoring, restoreError, hasCurrentSession, hasStoredToken, hasRole, landingPage, signIn, restore, signOut }
})
