import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { readAccessToken, setUnauthorizedHandler } from './api'
import { useSessionStore } from './stores/session'
import './styles/index.css'
import './styles/learner.css'

const pinia = createPinia()
setUnauthorizedHandler((token) => {
  if (token !== readAccessToken()) return
  const session = useSessionStore(pinia)
  const redirect = router.currentRoute.value.fullPath
  session.signOut()
  void router.replace({ path: '/login', query: { redirect, reason: 'expired' } })
})
createApp(App).use(pinia).use(router).mount('#app')
