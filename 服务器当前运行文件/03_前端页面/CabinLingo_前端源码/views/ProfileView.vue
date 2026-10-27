<template>
  <main class="app-shell page-shell"><LearnerHeader />
    <header class="section-header"><div><h1>我的</h1><p>CabinLingo 学习账户</p></div></header>
    <section class="profile-card"><div class="avatar">{{ session.displayName.slice(0, 1) }}</div><div><strong>{{ session.displayName }}</strong><span>CabinLingo 学员</span></div></section>
    <button class="setting-row" :aria-expanded="activePanel === 'security'" @click="togglePanel('security')">账号与安全 <i aria-hidden="true">›</i></button>
    <section v-if="activePanel === 'security'" class="setting-panel" aria-live="polite"><strong>企业账号安全</strong><p>账号、角色与密码由本单位管理员统一维护。如需重置密码，请联系管理员。</p></section>
    <button class="setting-row" :aria-expanded="activePanel === 'notifications'" @click="togglePanel('notifications')">通知设置 <i aria-hidden="true">›</i></button>
    <section v-if="activePanel === 'notifications'" class="setting-panel"><label><span><strong>任务提醒</strong><small>在平台内显示截止与反馈提醒</small></span><input v-model="notificationsEnabled" type="checkbox" @change="saveNotifications" /></label></section>
    <p v-if="savedMessage" class="saved-message" role="status">{{ savedMessage }}</p>
    <button class="logout-button" @click="logout">退出登录</button>
    <BottomNav />
  </main>
</template>
<script setup lang="ts">
import LearnerHeader from '@/components/LearnerHeader.vue'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import BottomNav from '@/components/BottomNav.vue'
import { useSessionStore } from '@/stores/session'
const session = useSessionStore()
const router = useRouter()
const activePanel = ref<'security' | 'notifications' | null>(null)
const notificationsEnabled = ref(localStorage.getItem('cabinlingo_notifications') !== 'off')
const savedMessage = ref('')
function togglePanel(panel: 'security' | 'notifications') { activePanel.value = activePanel.value === panel ? null : panel; savedMessage.value = '' }
function saveNotifications() { localStorage.setItem('cabinlingo_notifications', notificationsEnabled.value ? 'on' : 'off'); savedMessage.value = '通知偏好已保存在当前设备。' }
function logout() { session.signOut(); router.push('/login') }
</script>

<style scoped>
.setting-panel{margin:-4px 0 12px;padding:16px;border:1px solid var(--line);border-radius:var(--radius-md);background:var(--surface-soft);color:var(--ink)}
.setting-panel p{margin:7px 0 0;color:var(--ink-secondary);font-size:13px;line-height:1.65}
.setting-panel label{display:flex;align-items:center;justify-content:space-between;gap:18px}.setting-panel label span{display:grid;gap:5px}.setting-panel small{color:var(--ink-secondary)}
.setting-panel input{width:22px;height:22px;accent-color:var(--blue)}.saved-message{color:var(--success);font-size:12px}
</style>
