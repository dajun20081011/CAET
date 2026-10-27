<template>
  <main class="portal-layout">
    <aside class="portal-sidebar">
      <BrandMark /><p class="portal-label">管理端</p>
      <nav aria-label="管理端主导航"><button v-for="item in navItems" :key="item.path" class="portal-nav" :class="{ active: item.path === 'broadcast-scripts' }" @click="navigate(item.path)"><AppIcon :name="item.icon" /><span>{{ item.label }}</span></button></nav>
      <div class="portal-sidebar__footer"><span class="avatar">管</span><span><strong>{{ session.displayName }}</strong><small>管理员</small></span></div>
    </aside>
    <section class="portal-content">
      <header class="portal-header"><div><p class="portal-kicker">CabinLingo Console</p><h1>广播词库</h1></div><div class="portal-header__actions"><span class="staging-badge">LIVE DATA</span><button class="ghost-button" @click="logout">退出登录</button><span class="avatar avatar--small">管</span></div></header>
      <p v-if="error" class="notice notice--error" role="alert">{{ error }}</p>
      <p v-if="notice" class="notice notice--success" role="status">{{ notice }}</p>
      <div v-if="loading" class="panel loading-panel">正在读取广播词库…</div>
      <BroadcastScriptListPanel v-else-if="!selectedScript || !selectedVersion" :page="page" :organizations="organizations" @search="applyFilters" @page="changePage" @create="openCreate" @open="openScript" @toggle="toggleAvailability" />
      <BroadcastVersionEditor v-else :script="selectedScript" :version="selectedVersion" :slices="slices" :organizations="organizations" :full-text="fullText" :saving="saving" @update:full-text="value => fullText = value" @back="closeEditor" @save-meta="saveMetadata" @save-and-generate="saveAndGenerate" @complete="completeSave" @update-slice="updateSlice" @remove-slice="removeSlice" @move-slice="moveSlice" @add-slice="addSlice" />
    </section>

    <div v-if="creating" class="modal-backdrop" @click.self="creating = false">
      <form class="modal-card modal-card--wide" @submit.prevent="createScript">
        <div class="modal-heading"><div><h2>新建广播词</h2><p>输入正文后，系统将自动保存并切片</p></div><button type="button" class="modal-close" aria-label="关闭" @click="creating = false">×</button></div>
        <div class="create-grid">
          <label><span>广播词名称</span><input v-model.trim="createForm.title" maxlength="160" required @blur="syncCreateTitleLanguageSuffix"></label>
          <label><span>语言</span><select v-model="createForm.language" @change="syncCreateTitleLanguageSuffix"><option value="zh_cn">中文 zh_cn</option><option value="en_us">英文 en_us</option></select></label>
          <label><span>广播词类型</span><select v-model="createForm.script_type" required><option v-for="item in BROADCAST_SCRIPT_TYPE_OPTIONS" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
          <label><span>所属公司</span><select v-model="createForm.company_id"><option value="">全平台公共</option><option v-for="org in organizations" :key="org.id" :value="org.id">{{ org.name }}</option></select></label>
        </div>
        <label><span>完整标准正文</span><textarea v-model="createForm.full_text" rows="10" maxlength="500000" placeholder="输入完整广播词正文" required /></label>
        <div class="modal-actions"><button type="button" class="outline-button" @click="creating = false">取消</button><button class="primary-button primary-button--compact" :disabled="saving">{{ saving ? '创建中…' : '保存并自动切片' }}</button></div>
      </form>
    </div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { cabinlingoApi, type BroadcastScript, type BroadcastScriptPage, type BroadcastSlice, type BroadcastVersion, type Organization } from '@/api'
import AppIcon from '@/components/AppIcon.vue'
import BrandMark from '@/components/BrandMark.vue'
import BroadcastScriptListPanel from '@/components/BroadcastScriptListPanel.vue'
import BroadcastVersionEditor from '@/components/BroadcastVersionEditor.vue'
import { BROADCAST_SCRIPT_TYPE_OPTIONS, withBroadcastLanguageSuffix } from '@/domain/broadcastScripts'
import { useSessionStore } from '@/stores/session'

type ScriptFilters = { keyword?: string; language?: string; script_type?: string; company_id?: string; enabled?: boolean; archived?: boolean; page: number; page_size: number }
type HttpFailure = { response?: { data?: { detail?: string } } }
const router = useRouter(); const session = useSessionStore()
const navItems = [
  { path: 'dashboard', label: '工作台', icon: 'dashboard' }, { path: 'organizations', label: '组织班级', icon: 'organization' },
  { path: 'users', label: '用户管理', icon: 'users' }, { path: 'courses', label: '课程标准库', icon: 'course' },
  { path: 'broadcast-scripts', label: '广播词库', icon: 'collection' }, { path: 'tasks', label: '任务管理', icon: 'tasks' },
  { path: 'permissions', label: '权限管理', icon: 'lock' }, { path: 'ai', label: 'AI 评价规则', icon: 'ai' },
  { path: 'analytics', label: '数据分析', icon: 'trend' },
]
const loading = ref(true); const saving = ref(false); const error = ref(''); const notice = ref(''); const creating = ref(false)
const page = ref<BroadcastScriptPage>({ items: [], total: 0, page: 1, page_size: 20 })
const filters = reactive<ScriptFilters>({ page: 1, page_size: 20, archived: false })
const organizations = ref<Organization[]>([]); const selectedScript = ref<BroadcastScript | null>(null)
const versions = ref<BroadcastVersion[]>([]); const selectedVersion = ref<BroadcastVersion | null>(null)
const slices = ref<BroadcastSlice[]>([]); const fullText = ref('')
const createForm = reactive({ title: '', language: 'zh_cn', script_type: '通用广播', company_id: '', full_text: '' })

function navigate(path: string) { void router.push(`/admin/${path}`) }
function logout() { session.signOut(); void router.replace('/login') }
function failureMessage(cause: unknown, fallback: string) {
  const detail = (cause as HttpFailure)?.response?.data?.detail
  return typeof detail === 'string' && detail ? detail : fallback
}
function clearMessages() { error.value = ''; notice.value = '' }
async function fetchScripts() { page.value = await cabinlingoApi.broadcastScripts(filters) }
async function applyFilters(next: Omit<ScriptFilters, 'page_size'>) { Object.assign(filters, next, { page_size: 20 }); clearMessages(); try { await fetchScripts() } catch (cause) { error.value = failureMessage(cause, '广播词列表读取失败') } }
async function changePage(next: number) { filters.page = next; try { await fetchScripts() } catch (cause) { error.value = failureMessage(cause, '翻页失败') } }
function openCreate() { clearMessages(); Object.assign(createForm, { title: '', language: 'zh_cn', script_type: '通用广播', company_id: '', full_text: '' }); creating.value = true }
function syncCreateTitleLanguageSuffix() { createForm.title = withBroadcastLanguageSuffix(createForm.title, createForm.language) }
async function createScript() {
  if (!createForm.title || !createForm.script_type || !createForm.full_text.trim()) return
  saving.value = true; clearMessages()
  try {
    syncCreateTitleLanguageSuffix()
    const created = await cabinlingoApi.createBroadcastScript({ ...createForm, company_id: createForm.company_id || null })
    creating.value = false
    await fetchScripts(); await openScript(created); await saveAndGenerate()
  } catch (cause) { error.value = failureMessage(cause, '广播词创建失败') } finally { saving.value = false }
}
async function openScript(script: BroadcastScript) {
  loading.value = true; clearMessages()
  try {
    selectedScript.value = await cabinlingoApi.broadcastScript(script.id)
    versions.value = await cabinlingoApi.broadcastVersions(script.id)
    let current = versions.value[0]
    if (current.frozen) {
      current = await cabinlingoApi.createBroadcastVersion(script.id)
      versions.value = await cabinlingoApi.broadcastVersions(script.id)
    }
    await selectVersion(current)
  } catch (cause) { error.value = failureMessage(cause, '广播词详情读取失败') } finally { loading.value = false }
}
async function selectVersion(version: BroadcastVersion) {
  selectedVersion.value = await cabinlingoApi.broadcastVersion(version.id)
  fullText.value = selectedVersion.value.full_text
  slices.value = await cabinlingoApi.broadcastSlices(version.id)
}
function closeEditor() { selectedScript.value = null; selectedVersion.value = null; versions.value = []; slices.value = []; fullText.value = ''; clearMessages(); void fetchScripts() }
async function refreshSelection(versionId = selectedVersion.value?.id) {
  if (!selectedScript.value || !versionId) return
  selectedScript.value = await cabinlingoApi.broadcastScript(selectedScript.value.id)
  versions.value = await cabinlingoApi.broadcastVersions(selectedScript.value.id)
  const version = versions.value.find(item => item.id === versionId) || versions.value[0]
  selectedVersion.value = version
  fullText.value = version.full_text
  slices.value = await cabinlingoApi.broadcastSlices(version.id)
  await fetchScripts()
}
async function saveMetadata(payload: { title: string; language: string; script_type: string; company_id: string | null }) {
  if (!selectedScript.value) return
  saving.value = true; clearMessages()
  try { selectedScript.value = await cabinlingoApi.updateBroadcastScript(selectedScript.value.id, payload); notice.value = '广播词信息已保存。'; await fetchScripts() }
  catch (cause) { error.value = failureMessage(cause, '广播词信息保存失败') } finally { saving.value = false }
}
async function saveAndGenerate() {
  if (!selectedVersion.value) return
  if (!fullText.value.trim()) { error.value = '请先输入完整正文。'; return }
  saving.value = true; clearMessages()
  try {
    const result = await cabinlingoApi.saveBroadcastFullText(selectedVersion.value.id, fullText.value)
    selectedVersion.value = result.version
    versions.value = versions.value.map(item => item.id === result.version.id ? result.version : item)
    slices.value = await cabinlingoApi.generateBroadcastSlices(result.version.id)
    await refreshSelection(result.version.id)
    try {
      const queued = await cabinlingoApi.warmStandardPronunciations({
        text: fullText.value,
        language: selectedScript.value?.language === 'zh_cn' ? 'zh' : 'en',
        rate: 0.9,
      })
      notice.value = `正文已保存并自动切片；${queued.queued_token_count} 个词语的标准发音已进入后台生成队列${queued.truncated ? '（超长正文其余词语将在首次点击时补生成）' : ''}。`
    } catch {
      notice.value = '正文已保存并自动切片；标准发音预生成暂未启动，学员首次点击时将自动补生成。'
    }
  } catch (cause) { error.value = failureMessage(cause, '正文保存或自动切片失败') } finally { saving.value = false }
}
async function addSlice(payload: { text: string; verified: boolean }) {
  if (!selectedVersion.value) return
  saving.value = true; clearMessages()
  try { await cabinlingoApi.createBroadcastSlice(selectedVersion.value.id, payload); await refreshSelection(); notice.value = '切片已新增并自动重排。' }
  catch (cause) { error.value = failureMessage(cause, '新增切片失败') } finally { saving.value = false }
}
async function updateSlice(slice: BroadcastSlice, changes: { text?: string; verified?: boolean }) {
  saving.value = true; clearMessages()
  try { await cabinlingoApi.updateBroadcastSlice(slice.id, changes); await refreshSelection(); notice.value = '切片已保存。' }
  catch (cause) { error.value = failureMessage(cause, '切片保存失败') } finally { saving.value = false }
}
async function removeSlice(slice: BroadcastSlice) {
  if (!window.confirm(`确认删除第 ${slice.slice_no} 段？删除后编号会自动重排。`)) return
  saving.value = true; clearMessages()
  try { await cabinlingoApi.deleteBroadcastSlice(slice.id); await refreshSelection(); notice.value = '切片已删除并自动重排。' }
  catch (cause) { error.value = failureMessage(cause, '切片删除失败') } finally { saving.value = false }
}
async function moveSlice(index: number, direction: -1 | 1) {
  if (!selectedVersion.value) return
  const target = index + direction
  if (target < 0 || target >= slices.value.length) return
  const ordered = [...slices.value]; [ordered[index], ordered[target]] = [ordered[target], ordered[index]]
  saving.value = true; clearMessages()
  try { slices.value = await cabinlingoApi.orderBroadcastSlices(selectedVersion.value.id, ordered.map(item => item.id)); await refreshSelection(); notice.value = '切片顺序已保存。' }
  catch (cause) { error.value = failureMessage(cause, '切片排序失败') } finally { saving.value = false }
}
async function completeSave() {
  clearMessages()
  if (!selectedVersion.value || fullText.value !== selectedVersion.value.full_text) { error.value = '请先保存正文并自动切片。'; return }
  if (!slices.value.length || selectedVersion.value.slices_stale || slices.value.map(item => item.text).join('') !== fullText.value) { error.value = '切片与完整正文不一致，请调整后再完成。'; return }
  selectedScript.value = null; selectedVersion.value = null; versions.value = []; slices.value = []; fullText.value = ''
  await fetchScripts()
  notice.value = '广播词内容已完成保存，现在可在列表中启用。'
}
async function toggleAvailability(script: BroadcastScript) {
  if (script.enabled && !window.confirm(`停用“${script.title}”后，新任务将不能选择它。是否继续？`)) return
  saving.value = true; clearMessages()
  try {
    await cabinlingoApi.updateBroadcastScript(script.id, { enabled: !script.enabled })
    await fetchScripts()
    notice.value = script.enabled ? '广播词已停用，新任务不再可选。' : '广播词已启用，可投入任务发布。'
  } catch (cause) { error.value = failureMessage(cause, '使用状态更新失败') } finally { saving.value = false }
}
onMounted(async () => {
  try { const [organizationsResult] = await Promise.all([cabinlingoApi.organizations(), fetchScripts()]); organizations.value = organizationsResult }
  catch (cause) { error.value = failureMessage(cause, '广播词库初始化失败') } finally { loading.value = false }
})
</script>

<style scoped>
.portal-nav{width:100%;border:0;background:transparent;text-align:left}.notice{position:sticky;top:12px;z-index:20;margin:0 0 16px;padding:11px 14px;border:1px solid transparent;border-radius:10px;box-shadow:0 8px 24px #1637651a;font-size:12px}.notice--error{color:#9e4036;border-color:#f5c9c3;background:#fff0ee}.notice--success{color:#197455;border-color:#bfe8d7;background:#eaf9f2}.loading-panel{min-height:220px;display:grid;place-items:center;color:var(--muted)}.modal-backdrop{position:fixed;inset:0;z-index:50;display:grid;place-items:center;padding:20px;background:#08204d66}.modal-card{width:min(520px,100%);display:grid;gap:15px;padding:26px;border-radius:18px;background:#fff;box-shadow:0 24px 70px #08204d40}.modal-card--wide{width:min(760px,100%)}.modal-heading{display:flex;align-items:flex-start;justify-content:space-between}.modal-heading h2{margin:0 0 5px;font-size:19px}.modal-heading p{margin:0;color:var(--muted);font-size:12px}.modal-close{width:32px;height:32px;border:0;border-radius:50%;color:#7182a1;background:#f2f5fa;font-size:20px}.modal-card label{display:grid;gap:7px;color:#5d6f8d;font-size:12px;font-weight:600}.modal-card input,.modal-card select,.modal-card textarea{width:100%;padding:10px 12px;border:1px solid #dfe7f3;border-radius:9px;color:var(--ink);background:#fff}.modal-actions{display:flex;justify-content:flex-end;gap:9px}.create-grid{display:grid;grid-template-columns:1.4fr .7fr 1fr 1fr;gap:12px}@media(max-width:800px){.create-grid{grid-template-columns:1fr 1fr}}@media(max-width:700px){.create-grid{grid-template-columns:1fr}.modal-backdrop{align-items:end;padding:0}.modal-card{width:100%;max-height:92vh;overflow:auto;border-radius:24px 24px 0 0;padding:22px 18px}}
</style>
