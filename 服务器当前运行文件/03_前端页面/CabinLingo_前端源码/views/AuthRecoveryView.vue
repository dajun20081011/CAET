<template>
  <main class="auth-recovery page-shell">
    <BrandMark />
    <PageState
      :tone="retrying ? 'loading' : 'error'"
      title="暂时无法验证登录状态"
      :message="message"
      :action-label="retrying ? '' : '重新验证'"
      @action="retry"
    />
    <button class="auth-recovery__logout" type="button" :disabled="retrying" @click="useAnotherAccount">
      退出并使用其他账号
    </button>
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrandMark from '@/components/BrandMark.vue'
import PageState from '@/components/PageState.vue'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const retrying = ref(false)
const message = computed(() => session.restoreError || '请检查网络后重新验证，或使用其他账号登录。')
const redirect = computed(() => {
  const value = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  return value.startsWith('/') && !value.startsWith('//') && !value.startsWith('/auth-recovery')
    ? value : '/student/home'
})

async function retry() {
  if (retrying.value) return
  retrying.value = true
  try {
    const authenticated = await session.restore()
    if (authenticated) await router.replace(redirect.value)
    else if (!session.hasStoredToken()) await router.replace({ path: '/login', query: { reason: 'expired' } })
  } catch {
    // A failed identity check keeps the token and exposes the retry message.
  } finally {
    retrying.value = false
  }
}

async function useAnotherAccount() {
  session.signOut()
  await router.replace('/login')
}
</script>

<style scoped>
.auth-recovery{min-height:100svh;display:grid;place-content:center;gap:22px;width:min(560px,calc(100% - 32px));margin:auto;text-align:center}.auth-recovery :deep(.brand-mark){justify-content:center}.auth-recovery__logout{border:0;color:var(--muted);background:transparent;cursor:pointer}.auth-recovery__logout:disabled{opacity:.55;cursor:default}
</style>
