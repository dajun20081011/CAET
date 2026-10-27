<template>
  <section class="panel user-management-panel">
    <div class="panel__heading user-management-heading">
      <div>
        <p class="page-kicker">ACCOUNT DIRECTORY</p>
        <h2>账号与角色</h2>
        <p>按三端分区管理账号；删除后从当前列表移除，训练历史永久保留。</p>
      </div>
      <div class="account-actions">
        <button class="outline-button" type="button" @click="downloadTemplate"><AppIcon name="files" />下载模板</button>
        <button v-if="can('cabinlingo:user.import')" class="outline-button" type="button" @click="openImport"><AppIcon name="upload" />导入表格</button>
        <button class="outline-button" type="button" :disabled="!availableInstructors.length || !activeLearners.length" @click="openBulkInstructor"><AppIcon name="user" />批量绑定教员</button>
        <button class="primary-button primary-button--compact" type="button" @click="openManual"><AppIcon name="user" />手动添加</button>
        <input ref="fileInput" class="sr-only" type="file" accept=".csv,.tsv,text/csv,text/tab-separated-values" @change="readImportFile">
      </div>
    </div>

    <p class="security-note account-security-note"><AppIcon name="lock" />密码只保存不可逆哈希，无法查看原密码；具备权限的管理员可以重置密码，新的密码只在输入和提交时可见。</p>

    <div class="account-summary">
      <div><strong>{{ activeUsers.length }}</strong><span>全部账号</span></div>
      <div><strong>{{ countFor('student') }}</strong><span>学员端</span></div>
      <div><strong>{{ countFor('teacher') }}</strong><span>教员端</span></div>
      <div><strong>{{ countFor('admin') }}</strong><span>管理端</span></div>
    </div>

    <div class="user-segment-tabs" role="tablist" aria-label="账号端分类">
      <button v-for="group in groups" :key="group.key" type="button" role="tab" :aria-selected="segment === group.key" :class="{ active: segment === group.key }" @click="segment = group.key">
        <span>{{ group.label }}</span><b>{{ countFor(group.key) }}</b>
      </button>
    </div>

    <div class="content-list account-list">
      <article v-for="user in visibleUsers" :key="user.id" class="content-row account-row">
        <div class="avatar avatar--tiny">{{ user.display_name.slice(0, 1) }}</div>
        <div class="content-row__body">
          <strong>{{ user.display_name }}</strong>
          <small>{{ user.external_ref || user.email || '未填写账号' }} · {{ user.roles.map(roleLabel).join(' / ') || '未分配角色' }}</small>
        </div>
        <div class="account-row__meta">
          <span class="status-chip" :class="user.is_active ? 'published' : 'archived'">{{ user.is_active ? '启用' : '已停用' }}</span>
          <div class="account-row__actions">
            <button v-if="can('cabinlingo:user.password_reset')" class="outline-button outline-button--small" type="button" @click="openReset(user)">重置密码</button>
            <button v-if="roleGroup(user) === 'student'" class="outline-button outline-button--small" type="button" @click="openInstructor(user)">指定教员</button>
            <button v-if="can('cabinlingo:user.delete')" class="outline-button outline-button--small danger" type="button" :disabled="user.id === currentUserId || !user.is_active" :title="user.id === currentUserId ? '不能停用当前登录账号' : undefined" @click="deactivate(user)">{{ user.id === currentUserId ? '当前账号' : user.is_active ? '删除账号' : '已停用' }}</button>
          </div>
        </div>
      </article>
      <div v-if="!visibleUsers.length" class="empty-panel">当前分区暂无账号</div>
    </div>
    <p v-if="notice" class="account-notice" :class="{ error: noticeType === 'error' }" role="status">{{ notice }}</p>
  </section>

  <Teleport to="body">
  <div v-if="dialog" class="modal-backdrop" :class="{ 'modal-backdrop--drawer': dialog === 'instructor' }" role="presentation" @click.self="closeDialog">
    <form v-if="dialog === 'manual'" class="modal-card" @submit.prevent="saveManual">
      <div class="modal-heading"><div><h2>手动添加账号</h2><p>创建账号后分配到对应端和班级</p></div><button class="modal-close" type="button" aria-label="关闭对话框" @click="closeDialog">×</button></div>
      <label>账号 / 工号<input v-model.trim="manualForm.account" required maxlength="160" autocomplete="username"></label>
      <label>姓名<input v-model.trim="manualForm.display_name" required maxlength="160"></label>
      <label>初始密码<input v-model="manualForm.password" type="password" minlength="10" required autocomplete="new-password"><small class="field-hint">至少 10 个字符；系统不会保存明文。</small></label>
      <label>所属端<select v-model="manualForm.role"><option value="learner">学员端</option><option value="instructor">教员端</option><option value="evaluator">教员端 · 测评员</option><option value="admin">管理端</option></select></label>
      <label>班级（可选）<select v-model="manualForm.class_id"><option value="">暂不分班</option><option v-for="item in classes" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
      <label>邮箱（可选）<input v-model.trim="manualForm.email" type="email" maxlength="320"></label>
      <p v-if="dialogError" class="dialog-error-inline" role="alert">{{ dialogError }}</p>
      <div class="modal-actions"><button class="outline-button" type="button" @click="closeDialog">取消</button><button class="primary-button primary-button--compact" type="submit" :disabled="busy">{{ busy ? '保存中…' : '创建账号' }}</button></div>
    </form>

    <form v-else-if="dialog === 'reset'" class="modal-card" @submit.prevent="saveReset">
      <div class="modal-heading"><div><h2>重置密码</h2><p>{{ selectedUser?.display_name }} · {{ selectedUser?.external_ref || '当前账号' }}</p></div><button class="modal-close" type="button" aria-label="关闭对话框" @click="closeDialog">×</button></div>
      <p class="security-note"><AppIcon name="lock" />原密码无法读取。提交后旧会话立即失效，请将新密码安全交给账号本人。</p>
      <label>新密码<input v-model="resetPassword" type="password" minlength="10" required autocomplete="new-password"></label>
      <p v-if="dialogError" class="dialog-error-inline" role="alert">{{ dialogError }}</p>
      <div class="modal-actions"><button class="outline-button" type="button" @click="closeDialog">取消</button><button class="primary-button primary-button--compact" type="submit" :disabled="busy">{{ busy ? '提交中…' : '确认重置' }}</button></div>
    </form>

    <section v-else-if="dialog === 'instructor'" class="instructor-drawer" role="dialog" aria-modal="true" aria-labelledby="instructor-drawer-title">
      <header class="instructor-drawer__header modal-heading"><div><h2 id="instructor-drawer-title">绑定教员</h2><p>{{ selectedUser?.display_name }} · 勾选后一次确认，无需滚动到页面底部</p></div><button class="modal-close" type="button" aria-label="关闭教员列表" @click="closeDialog">×</button></header>
      <div class="instructor-drawer__body">
        <label class="drawer-field">负责范围<select v-model="assignmentForm.assignment_type"><option value="training">负责训练</option><option value="assessment">负责考核</option><option value="both">训练 + 考核</option></select></label>
        <label class="drawer-field">查找教员<input ref="instructorSearchInput" v-model.trim="instructorQuery" type="search" placeholder="输入姓名、工号或邮箱" autocomplete="off"></label>
        <div class="instructor-picker" aria-label="可选教员列表">
          <label v-for="item in filteredInstructors" :key="item.id" class="instructor-option" :class="{ selected: selectedInstructorIds.includes(item.id), bound: activeInstructorIds.has(item.id) }">
            <input v-model="selectedInstructorIds" type="checkbox" :value="item.id" :disabled="busy || activeInstructorIds.has(item.id)">
            <span class="avatar avatar--tiny">{{ item.display_name.slice(0, 1) }}</span>
            <span><strong>{{ item.display_name }}</strong><small>{{ item.external_ref || item.email || '教员账号' }} · {{ item.roles.map(roleLabel).join(' / ') }}</small></span>
            <b v-if="activeInstructorIds.has(item.id)">已绑定</b>
          </label>
          <p v-if="busy && !instructorAssignments.length" class="drawer-empty">正在加载绑定关系…</p>
          <p v-else-if="!filteredInstructors.length" class="drawer-empty">没有符合条件的启用教员</p>
        </div>

        <section v-if="instructorAssignments.length" class="current-assignments" aria-label="当前绑定">
          <h3>当前绑定</h3>
          <div class="assignment-list"><article v-for="item in instructorAssignments" :key="item.id" class="assignment-row"><div><strong>{{ item.instructor_name }}</strong><small>{{ item.instructor_account || '教员账号' }}<template v-if="item.course_title"> · {{ item.course_title }}</template></small></div><select v-model="item.assignment_type" :disabled="busy || item.status !== 'active'" aria-label="负责范围" @change="updateInstructor(item)"><option value="training">训练</option><option value="assessment">考核</option><option value="both">训练 + 考核</option></select><span class="status-chip" :class="item.status === 'active' ? 'published' : 'archived'">{{ item.status === 'active' ? '生效' : '已停用' }}</span><button v-if="item.status === 'active'" type="button" class="outline-button outline-button--small danger" :disabled="busy" @click="removeInstructor(item)">移除</button></article></div>
        </section>
        <p v-else-if="!busy" class="drawer-empty">尚未绑定教员。学员提交后会标记为“未分配教员”。</p>
        <p v-if="dialogError" class="dialog-error-inline" role="alert">{{ dialogError }}</p>
      </div>
      <footer class="instructor-drawer__footer"><span>已勾选 {{ selectedInstructorIds.length }} 名</span><div><button class="outline-button" type="button" :disabled="busy" @click="closeDialog">取消</button><button class="primary-button primary-button--compact" type="button" :disabled="busy || !selectedInstructorIds.length" @click="confirmInstructors">{{ busy ? '绑定中…' : `确认绑定（${selectedInstructorIds.length}）` }}</button></div></footer>
    </section>

    <form v-else-if="dialog === 'bulkInstructor'" class="modal-card modal-card--wide modal-card--bulk" @submit.prevent="saveBulkInstructor">
      <div class="modal-heading"><div><h2>批量绑定教员</h2><p>选择一名教员和多个学员，一次完成绑定；已有相同关系不会重复创建。</p></div><button class="modal-close" type="button" aria-label="关闭对话框" @click="closeDialog">×</button></div>
      <div class="bulk-assignment-settings"><label>教员<select v-model="bulkAssignmentForm.instructor_id" required><option value="" disabled>请选择教员</option><option v-for="item in availableInstructors" :key="item.id" :value="item.id">{{ item.display_name }} · {{ item.external_ref || item.email || '教员账号' }}</option></select></label><label>负责范围<select v-model="bulkAssignmentForm.assignment_type"><option value="training">负责训练</option><option value="assessment">负责考核</option><option value="both">训练 + 考核</option></select></label></div>
      <div class="bulk-class-picker"><strong>按班级整体绑定</strong><small>班级成员由服务端展开，并与下方指定学员自动去重。</small><div><label v-for="item in activeClasses" :key="item.id" :class="{ selected: bulkAssignmentForm.class_ids.includes(item.id) }"><input v-model="bulkAssignmentForm.class_ids" type="checkbox" :value="item.id"><span>{{ item.name }}</span><small>{{ item.member_count }} 人</small></label><p v-if="!activeClasses.length" class="field-hint">暂无启用班级</p></div></div>
      <label>补充指定学员<input v-model.trim="bulkLearnerQuery" type="search" placeholder="输入姓名或账号"></label>
      <div class="bulk-picker-toolbar"><span>已选择 <strong>{{ bulkAssignmentForm.class_ids.length }}</strong> 个班级、<strong>{{ bulkAssignmentForm.student_ids.length }}</strong> 名指定学员</span><div><button type="button" @click="toggleFilteredLearners">{{ allFilteredLearnersSelected ? '取消当前结果' : '全选当前结果' }}</button><button v-if="bulkAssignmentForm.student_ids.length" type="button" @click="bulkAssignmentForm.student_ids = []">清空学员</button></div></div>
      <div class="bulk-learner-picker"><label v-for="learner in filteredBulkLearners" :key="learner.id" class="bulk-learner-option" :class="{ selected: bulkAssignmentForm.student_ids.includes(learner.id) }"><input v-model="bulkAssignmentForm.student_ids" type="checkbox" :value="learner.id"><span><strong>{{ learner.display_name }}</strong><small>{{ learner.external_ref || learner.email || '未填写账号' }}</small></span></label><p v-if="!filteredBulkLearners.length" class="field-hint">没有符合条件的启用学员</p></div>
      <p v-if="dialogError" class="dialog-error-inline" role="alert">{{ dialogError }}</p>
      <div class="modal-actions"><button class="outline-button" type="button" @click="closeDialog">取消</button><button class="primary-button primary-button--compact" type="submit" :disabled="busy || !bulkAssignmentForm.instructor_id || (!bulkAssignmentForm.student_ids.length && !bulkAssignmentForm.class_ids.length)">{{ busy ? '绑定中…' : '确认批量绑定' }}</button></div>
    </form>

    <section v-else-if="dialog === 'import'" class="modal-card modal-card--wide">
      <div class="modal-heading"><div><h2>导入账号表格</h2><p>支持 CSV / TSV（UTF-8、GBK/GB18030）。</p></div><button class="modal-close" type="button" aria-label="关闭对话框" @click="closeDialog">×</button></div>
      <p class="file-note">表头：account、display_name、password、role、email、class_id；角色可填 learner / instructor / evaluator / admin，也支持中文角色。</p>
      <button class="upload-dropzone" type="button" @click="fileInput?.click()"><AppIcon name="upload" /><strong>{{ importFilename || '选择 CSV / TSV 文件' }}</strong><small>最多 500 行；重复账号会逐行报告，不影响其他行。</small></button>
      <div v-if="importRows.length" class="import-preview"><strong>待导入 {{ importRows.length }} 行</strong><span>账号、姓名和初始密码已清理首尾空格；密码长度已逐行校验。</span><ul><li v-for="(row, index) in importRows.slice(0, 4)" :key="index">{{ row.account }} · {{ row.display_name }} · {{ roleLabel(row.role) }} · 密码 {{ row.password.length }} 字符</li></ul><small v-if="importRows.length > 4">以及其他 {{ importRows.length - 4 }} 行…</small></div>
      <p v-if="importResult" class="import-result" :class="{ error: importResult.failed > 0 }">导入完成：成功 {{ importResult.imported }} 行，失败 {{ importResult.failed }} 行。</p>
      <ul v-if="importResult?.errors.length" class="import-errors"><li v-for="item in importResult.errors" :key="`${item.row}-${item.account}`">第 {{ item.row }} 行 {{ item.account || '未命名' }}：{{ item.message }}</li></ul>
      <p v-if="dialogError" class="dialog-error-inline" role="alert">{{ dialogError }}</p>
      <div class="modal-actions"><button class="outline-button" type="button" @click="closeDialog">关闭</button><button class="primary-button primary-button--compact" type="button" :disabled="busy || !importRows.length" @click="saveImport">{{ busy ? '导入中…' : '开始导入' }}</button></div>
    </section>
  </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { cabinlingoApi, type InstructorAssignment, type TrainingClass, type UserImportResult, type UserSummary } from '@/api'
import { decodeImportText } from '@/utils/importText'

const props = defineProps<{ users: UserSummary[]; classes: TrainingClass[]; currentPermissions: string[]; currentUserId?: string }>()
const emit = defineEmits<{ changed: [] }>()
type Segment = 'all' | 'student' | 'teacher' | 'admin'
type Dialog = 'manual' | 'reset' | 'import' | 'instructor' | 'bulkInstructor' | null
const groups: Array<{ key: Segment; label: string }> = [{ key: 'all', label: '全部账号' }, { key: 'student', label: '学员端' }, { key: 'teacher', label: '教员端' }, { key: 'admin', label: '管理端' }]
const segment = ref<Segment>('all')
const dialog = ref<Dialog>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const busy = ref(false)
const notice = ref('')
const noticeType = ref<'success' | 'error'>('success')
const dialogError = ref('')
const selectedUser = ref<UserSummary | null>(null)
const resetPassword = ref('')
const importFilename = ref('')
const importRows = ref<Array<{ account: string; display_name: string; password: string; role: string; email?: string; class_id?: string }>>([])
const importResult = ref<UserImportResult | null>(null)
const hiddenUserIds = ref<string[]>([])
const manualForm = ref({ account: '', display_name: '', password: '', role: 'learner', email: '', class_id: '' })
const instructorAssignments = ref<InstructorAssignment[]>([])
const assignmentForm = ref({ assignment_type: 'both' as 'training' | 'assessment' | 'both' })
const selectedInstructorIds = ref<string[]>([])
const instructorQuery = ref('')
const instructorSearchInput = ref<HTMLInputElement | null>(null)
const bulkAssignmentForm = ref({ instructor_id: '', assignment_type: 'both' as 'training' | 'assessment' | 'both', student_ids: [] as string[], class_ids: [] as string[] })
const bulkLearnerQuery = ref('')
const availableInstructors = computed(() => props.users.filter(user => user.is_active && user.roles.some(role => role === 'instructor' || role === 'evaluator')))
const activeInstructorIds = computed(() => new Set(instructorAssignments.value.filter(item => item.status === 'active').map(item => item.instructor_id)))
const filteredInstructors = computed(() => {
  const query = instructorQuery.value.toLowerCase()
  return availableInstructors.value.filter(user => !query || `${user.display_name} ${user.external_ref || ''} ${user.email || ''}`.toLowerCase().includes(query))
})
const activeClasses = computed(() => props.classes.filter(item => item.status === 'active'))

function roleGroup(user: UserSummary): Segment { if (user.roles.includes('admin')) return 'admin'; if (user.roles.some(role => role === 'instructor' || role === 'evaluator')) return 'teacher'; return 'student' }
function roleLabel(role: string): string { return ({ learner: '学员', instructor: '教员', evaluator: '测评员', admin: '管理员' } as Record<string, string>)[role] || role }
function can(permission: string): boolean { return props.currentPermissions.includes(permission) || props.currentPermissions.includes('cabinlingo:admin') }
const activeUsers = computed(() => props.users.filter(user => user.is_active && !hiddenUserIds.value.includes(user.id)))
const activeLearners = computed(() => activeUsers.value.filter(user => roleGroup(user) === 'student'))
const filteredBulkLearners = computed(() => { const query = bulkLearnerQuery.value.toLowerCase(); return activeLearners.value.filter(user => !query || `${user.display_name} ${user.external_ref || ''} ${user.email || ''}`.toLowerCase().includes(query)) })
const allFilteredLearnersSelected = computed(() => filteredBulkLearners.value.length > 0 && filteredBulkLearners.value.every(user => bulkAssignmentForm.value.student_ids.includes(user.id)))
function countFor(group: Segment): number { return group === 'all' ? activeUsers.value.length : activeUsers.value.filter(user => roleGroup(user) === group).length }
const visibleUsers = computed(() => segment.value === 'all' ? activeUsers.value : activeUsers.value.filter(user => roleGroup(user) === segment.value))
function openManual() { dialogError.value = ''; manualForm.value = { account: '', display_name: '', password: '', role: 'learner', email: '', class_id: '' }; dialog.value = 'manual' }
function openReset(user: UserSummary) { dialogError.value = ''; selectedUser.value = user; resetPassword.value = ''; dialog.value = 'reset' }
async function openInstructor(user: UserSummary) {
  dialogError.value = ''; selectedUser.value = user; assignmentForm.value = { assignment_type: 'both' }; selectedInstructorIds.value = []; instructorQuery.value = ''; dialog.value = 'instructor'; busy.value = true
  await nextTick(); instructorSearchInput.value?.focus()
  try { instructorAssignments.value = await cabinlingoApi.learnerInstructors(user.id) } catch { instructorAssignments.value = []; dialogError.value = '指定教员读取失败，请刷新后重试' } finally { busy.value = false }
}
function openBulkInstructor() { dialogError.value = ''; bulkLearnerQuery.value = ''; bulkAssignmentForm.value = { instructor_id: availableInstructors.value[0]?.id || '', assignment_type: 'both', student_ids: [], class_ids: [] }; dialog.value = 'bulkInstructor' }
function toggleFilteredLearners() { const filteredIds = filteredBulkLearners.value.map(user => user.id); bulkAssignmentForm.value.student_ids = allFilteredLearnersSelected.value ? bulkAssignmentForm.value.student_ids.filter(id => !filteredIds.includes(id)) : [...new Set([...bulkAssignmentForm.value.student_ids, ...filteredIds])] }
async function saveBulkInstructor() { if (!bulkAssignmentForm.value.instructor_id || (!bulkAssignmentForm.value.student_ids.length && !bulkAssignmentForm.value.class_ids.length)) return; busy.value = true; dialogError.value = ''; try { const result = await cabinlingoApi.batchCreateInstructorAssignments({ instructor_id: bulkAssignmentForm.value.instructor_id, assignment_type: bulkAssignmentForm.value.assignment_type, student_ids: [...bulkAssignmentForm.value.student_ids], class_ids: [...bulkAssignmentForm.value.class_ids] }); closeDialog(); emit('changed'); const changed = result.created + result.reactivated; const suffix = result.unchanged ? `，${result.unchanged} 人已有相同绑定` : ''; const reviewSuffix = result.evaluation_tasks_created ? `，补分配 ${result.evaluation_tasks_created} 条评价任务` : ''; showNotice(`已处理 ${result.selected} 名学员，新建或恢复 ${changed} 人${suffix}${reviewSuffix}`) } catch { dialogError.value = '批量绑定失败，请确认教员、班级和学员账号均处于启用状态'; busy.value = false } }
async function confirmInstructors() {
  if (!selectedUser.value || !selectedInstructorIds.value.length) return
  const studentId = selectedUser.value.id
  busy.value = true; dialogError.value = ''
  let created = 0
  try {
    for (const instructorId of selectedInstructorIds.value) {
      await cabinlingoApi.createInstructorAssignment(studentId, { instructor_id: instructorId, assignment_type: assignmentForm.value.assignment_type })
      created += 1
    }
    try {
      const result = await cabinlingoApi.reassignEvaluationTasks(studentId)
      showNotice(result.created ? `已绑定 ${created} 名教员，并补分配 ${result.created} 条评价任务` : `已绑定 ${created} 名教员`)
    } catch { showNotice(`已绑定 ${created} 名教员；历史未分配任务将在下一次同步时处理`, 'error') }
    closeDialog(); emit('changed')
  } catch {
    instructorAssignments.value = await cabinlingoApi.learnerInstructors(studentId).catch(() => instructorAssignments.value)
    selectedInstructorIds.value = selectedInstructorIds.value.filter(id => !activeInstructorIds.value.has(id))
    dialogError.value = created ? `已绑定 ${created} 名；其余绑定失败，请确认账号状态后重试。` : '绑定失败，请确认选择的是启用中的教员账号。'
    busy.value = false
  }
}
async function updateInstructor(item: InstructorAssignment) { if (!selectedUser.value) return; busy.value = true; dialogError.value = ''; try { await cabinlingoApi.updateInstructorAssignment(selectedUser.value.id, item.id, { assignment_type: item.assignment_type }); try { await cabinlingoApi.reassignEvaluationTasks(selectedUser.value.id) } catch { /* Binding is already saved; migration sync can be retried later. */ } showNotice('负责范围已更新') } catch { dialogError.value = '负责范围更新失败' } finally { busy.value = false } }
async function removeInstructor(item: InstructorAssignment) { if (!selectedUser.value || !window.confirm(`确认移除 ${item.instructor_name} 的绑定？历史评价不会删除。`)) return; busy.value = true; try { await cabinlingoApi.deactivateInstructorAssignment(selectedUser.value.id, item.id); instructorAssignments.value = await cabinlingoApi.learnerInstructors(selectedUser.value.id); showNotice('绑定已停用；只影响未来提交') } catch { dialogError.value = '绑定移除失败' } finally { busy.value = false } }
function openImport() { dialogError.value = ''; importFilename.value = ''; importRows.value = []; importResult.value = null; if (fileInput.value) fileInput.value.value = ''; dialog.value = 'import' }
function closeDialog() { dialog.value = null; busy.value = false; dialogError.value = ''; selectedInstructorIds.value = []; instructorQuery.value = '' }
function showNotice(message: string, type: 'success' | 'error' = 'success') { notice.value = message; noticeType.value = type; window.setTimeout(() => { notice.value = '' }, 4500) }
async function saveManual() { busy.value = true; dialogError.value = ''; try { await cabinlingoApi.createUser({ ...manualForm.value, role: manualForm.value.role as 'learner' | 'evaluator' | 'instructor' | 'admin', email: manualForm.value.email || undefined, class_id: manualForm.value.class_id || undefined }); closeDialog(); emit('changed'); showNotice('账号创建成功') } catch { dialogError.value = '账号创建失败，请检查账号、邮箱是否重复，密码是否至少 10 个字符'; busy.value = false } }
async function saveReset() { if (!selectedUser.value) return; busy.value = true; dialogError.value = ''; try { await cabinlingoApi.resetUserPassword(selectedUser.value.id, resetPassword.value); closeDialog(); showNotice('密码已重置；原密码不可恢复') } catch { dialogError.value = '密码重置失败，请确认权限和密码长度'; busy.value = false } }
async function deactivate(user: UserSummary) { if (!user.is_active || user.id === props.currentUserId) return; if (!window.confirm(`确定停用账号“${user.display_name}”吗？训练历史会保留。`)) return; hiddenUserIds.value = [...hiddenUserIds.value, user.id]; try { await cabinlingoApi.deactivateUser(user.id); emit('changed'); showNotice('账号已删除，历史训练数据已保留') } catch { hiddenUserIds.value = hiddenUserIds.value.filter(id => id !== user.id); showNotice('账号删除失败，请检查权限或查看服务端日志', 'error') } }
function normalizeHeader(value: string): string { return value.replace(/^\uFEFF/, '').trim().toLowerCase().replace(/[ _-]/g, '') }
function parseDelimited(text: string, delimiter: ',' | '\t'): string[][] { const rows: string[][] = []; let row: string[] = []; let cell = ''; let quoted = false; for (let index = 0; index < text.length; index += 1) { const char = text[index]; const next = text[index + 1]; if (char === '"' && quoted && next === '"') { cell += '"'; index += 1 } else if (char === '"') quoted = !quoted; else if (char === delimiter && !quoted) { row.push(cell); cell = '' } else if ((char === '\n' || char === '\r') && !quoted) { if (char === '\r' && next === '\n') index += 1; row.push(cell); if (row.some(value => value.trim())) rows.push(row); row = []; cell = '' } else cell += char } if (cell || row.length) { row.push(cell); if (row.some(value => value.trim())) rows.push(row) } return rows }
function mapRole(value: string): string { const normalized = value.trim().toLowerCase(); return ({ 学员: 'learner', 学员端: 'learner', learner: 'learner', 教员: 'instructor', 教员端: 'instructor', instructor: 'instructor', 测评员: 'evaluator', evaluator: 'evaluator', 管理员: 'admin', 管理端: 'admin', admin: 'admin' } as Record<string, string>)[normalized] || normalized }
async function readImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]; if (!file) return
  dialogError.value = ''; importResult.value = null; importFilename.value = file.name
  try {
    const { text } = decodeImportText(await file.arrayBuffer())
    const delimiter = file.name.toLowerCase().endsWith('.tsv') ? '\t' : ','
    const rows = parseDelimited(text, delimiter)
    if (rows.length < 2) throw new Error('文件至少需要表头和一行数据')
    const headers = rows[0].map(normalizeHeader)
    const aliases: Record<string, string[]> = { account: ['account', '账号', '工号', '登录名'], display_name: ['displayname', '姓名', '名称'], password: ['password', '密码', '初始密码'], role: ['role', '角色', '端'], email: ['email', '邮箱'], class_id: ['classid', '班级id', '班级ID'] }
    const indexes: Record<string, number> = {}
    for (const [field, names] of Object.entries(aliases)) indexes[field] = headers.findIndex(header => names.map(normalizeHeader).includes(header))
    if (indexes.account < 0 || indexes.display_name < 0 || indexes.password < 0) throw new Error('缺少必需表头：account、display_name、password')
    const parsed = rows.slice(1).map(values => ({
      account: (values[indexes.account] || '').trim(),
      display_name: (values[indexes.display_name] || '').trim(),
      password: (values[indexes.password] || '').trim(),
      role: mapRole(indexes.role >= 0 ? values[indexes.role] || 'learner' : 'learner'),
      email: indexes.email >= 0 ? (values[indexes.email] || '').trim() || undefined : undefined,
      class_id: indexes.class_id >= 0 ? (values[indexes.class_id] || '').trim() || undefined : undefined,
    })).filter(row => row.account || row.display_name || row.password)
    if (!parsed.length) throw new Error('没有可导入的数据行')
    const allowedRoles = new Set(['learner', 'instructor', 'evaluator', 'admin'])
    const seen = new Set<string>()
    parsed.forEach((row, index) => {
      const rowNumber = index + 2
      if (!row.account || !row.display_name) throw new Error(`第 ${rowNumber} 行账号或姓名为空`)
      if (/^\d+(?:\.\d+)?e[+-]?\d+$/i.test(row.account)) throw new Error(`第 ${rowNumber} 行账号被表格转成科学计数法，请先将账号列设为文本`)
      if (row.password.length < 10) throw new Error(`第 ${rowNumber} 行密码不足 10 个字符`)
      if (!allowedRoles.has(row.role)) throw new Error(`第 ${rowNumber} 行角色无效：${row.role}`)
      const accountKey = row.account.toLowerCase()
      if (seen.has(accountKey)) throw new Error(`第 ${rowNumber} 行账号在文件中重复：${row.account}`)
      seen.add(accountKey)
    })
    importRows.value = parsed
  } catch (error) { importRows.value = []; dialogError.value = error instanceof Error ? error.message : '表格解析失败' }
}
async function saveImport() { if (!importRows.value.length) return; busy.value = true; dialogError.value = ''; try { importResult.value = await cabinlingoApi.importUsers(importRows.value); emit('changed'); showNotice(`表格导入完成：成功 ${importResult.value.imported} 行，失败 ${importResult.value.failed} 行`); busy.value = false } catch { dialogError.value = '表格导入失败，请检查文件格式、权限和服务端迁移'; busy.value = false } }
function downloadTemplate() { const csv = '\uFEFFaccount,display_name,password,role,email,class_id\nuser001,张三,ChangeMe123!,learner,,\nteacher001,李教员,ChangeMe123!,instructor,,\n'; const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'cabinlingo-user-import-template.csv'; link.click(); URL.revokeObjectURL(link.href) }
</script>

<style scoped>
.modal-backdrop{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:20px;background:#08204d66;backdrop-filter:blur(3px)}.modal-card{display:grid;gap:15px;width:min(520px,100%);max-height:calc(100dvh - 40px);overflow-y:auto;padding:26px;border-radius:18px;background:#fff;box-shadow:0 24px 70px #08204d40}.modal-card--wide{width:min(680px,100%)}.modal-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.modal-heading h2{margin:0 0 5px;color:var(--ink);font-size:19px}.modal-heading p{margin:0;color:var(--muted);font-size:12px}.modal-close{display:grid;place-items:center;flex:none;width:44px;height:44px;border:0;border-radius:50%;color:#7182a1;background:#f2f5fa;font-size:22px}.modal-card label{display:grid;gap:7px;color:var(--ink-secondary);font-size:12px;font-weight:600}.modal-card input,.modal-card select,.modal-card textarea{width:100%;min-height:44px;padding:10px 12px;border:1px solid var(--line);border-radius:9px;color:var(--ink);background:#fff}.modal-actions{display:flex;justify-content:flex-end;gap:9px}.modal-actions button{min-height:44px}
.modal-card--bulk{max-height:calc(100vh - 40px);overflow-y:auto}.bulk-class-picker{display:grid;gap:7px}.bulk-class-picker>strong,.bulk-class-picker>small{display:block}.bulk-class-picker>small{color:var(--muted);font-size:10px}.bulk-class-picker>div{display:flex;flex-wrap:wrap;gap:7px;max-height:120px;overflow:auto;padding:9px;border:1px solid var(--line);border-radius:10px;background:var(--surface-soft)}.bulk-class-picker>div label{display:flex!important;align-items:center;gap:6px;padding:7px 9px;border:1px solid transparent;border-radius:8px;background:#fff;font-weight:400!important}.bulk-class-picker>div label.selected{border-color:#8ebaff;background:var(--blue-soft)}.bulk-class-picker input{width:auto!important}.bulk-class-picker label small{color:var(--muted);font-size:9px}.user-management-heading{align-items:flex-start}.account-actions{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:8px}.account-actions button{display:inline-flex;align-items:center;gap:6px;min-height:42px}.account-security-note{margin:0 0 18px}.account-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0 18px}.account-summary div{padding:13px 14px;border:1px solid var(--line);border-radius:12px;background:var(--surface-soft)}.account-summary strong,.account-summary span{display:block}.account-summary strong{font-size:23px;color:var(--ink)}.account-summary span{margin-top:3px;color:var(--muted);font-size:11px}.user-segment-tabs{display:flex;gap:8px;overflow:auto;margin-bottom:6px;padding-bottom:2px;border-bottom:1px solid var(--line)}.user-segment-tabs button{display:flex;align-items:center;gap:8px;min-height:44px;padding:0 15px;border:0;border-bottom:2px solid transparent;color:var(--muted);background:transparent;white-space:nowrap}.user-segment-tabs button.active{border-bottom-color:var(--blue);color:var(--blue);font-weight:700}.user-segment-tabs b{min-width:20px;padding:2px 6px;border-radius:9px;color:inherit;background:var(--surface-soft);font-size:10px}.account-row{align-items:center}.account-row__meta{display:flex;align-items:center;gap:12px}.account-row__actions{display:flex;gap:7px}.account-row__actions button{min-height:34px}.field-hint{color:var(--muted);font-size:10px;font-weight:400}.dialog-error-inline{margin:0;padding:10px;border-radius:9px;color:#a84040;background:#fff0f0;font-size:12px}.account-notice{margin:15px 0 0;padding:10px 12px;border-radius:9px;color:#287b62;background:#eaf9f2;font-size:12px}.account-notice.error{color:#a84040;background:#fff0f0}.bulk-assignment-settings{display:grid;grid-template-columns:1fr 1fr;gap:10px}.bulk-picker-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;color:var(--ink-secondary);font-size:11px}.bulk-picker-toolbar>div{display:flex;gap:6px}.bulk-picker-toolbar button{padding:6px 9px;border:1px solid #c8dcfa;border-radius:7px;color:var(--blue);background:#fff;font-size:10px}.bulk-learner-picker{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;max-height:280px;overflow:auto;padding:10px;border:1px solid var(--line);border-radius:11px;background:var(--surface-soft)}.bulk-learner-option{display:flex!important;align-items:center;gap:9px;min-width:0;padding:10px;border:1px solid transparent;border-radius:9px;background:#fff;font-weight:400!important}.bulk-learner-option.selected{border-color:#8ebaff;background:var(--blue-soft)}.bulk-learner-option input{width:auto!important}.bulk-learner-option span{min-width:0}.bulk-learner-option strong,.bulk-learner-option small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.bulk-learner-option strong{color:var(--ink);font-size:12px}.bulk-learner-option small{margin-top:3px;color:var(--muted);font-size:10px}.upload-dropzone{display:grid;justify-items:center;gap:7px;min-height:130px;padding:18px;border:1px dashed #a9c8f3;border-radius:14px;color:var(--blue);background:#f5f9ff}.upload-dropzone .app-icon{width:28px;height:28px}.upload-dropzone strong{color:var(--ink);font-size:14px}.upload-dropzone small{color:var(--muted);font-size:11px}.import-preview{display:grid;gap:6px;padding:12px;border-radius:10px;background:var(--surface-soft);font-size:12px}.import-preview span,.import-preview small{color:var(--muted);font-size:11px}.import-preview ul,.import-errors{margin:3px 0 0;padding-left:19px;color:var(--ink-secondary);font-size:11px;line-height:1.7}.import-result{margin:0;padding:10px;border-radius:9px;color:#287b62;background:#eaf9f2;font-size:12px}.import-result.error{color:#a84040;background:#fff0f0}.import-errors{max-height:130px;overflow:auto;margin:0;padding:10px 12px 10px 27px;border-radius:9px;color:#a84040;background:#fff0f0}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}@media(max-width:720px){.user-management-heading{display:grid;gap:14px}.account-actions{justify-content:flex-start}.account-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.bulk-assignment-settings,.bulk-learner-picker{grid-template-columns:1fr}.account-row{align-items:flex-start;flex-wrap:wrap}.account-row__meta{width:100%;padding-left:44px;justify-content:space-between}.account-row__actions{flex-wrap:wrap}.account-row__actions button{min-height:40px}}@media(max-width:480px){.account-actions button{flex:1}.bulk-picker-toolbar{align-items:flex-start;flex-direction:column}.account-row__meta{padding-left:0}.account-row__meta,.account-row__actions{align-items:flex-start;flex-direction:column}.account-row__actions button{width:100%}}
.modal-backdrop--drawer{display:flex;align-items:stretch;justify-content:flex-end;padding:0}.instructor-drawer{display:flex;flex-direction:column;width:min(480px,100%);height:100dvh;border-left:1px solid #dce6f4;background:#fff;box-shadow:-24px 0 70px #08204d33;animation:drawer-in .2s ease-out}.instructor-drawer__header{flex:none;margin:0;padding:22px 22px 16px;border-bottom:1px solid var(--line)}.instructor-drawer__header h2{margin:0 0 5px;color:var(--ink);font-size:20px}.instructor-drawer__header p{margin:0;color:var(--muted);font-size:11px;line-height:1.5}.instructor-drawer__body{display:grid;align-content:start;gap:15px;min-height:0;overflow-y:auto;padding:18px 22px}.drawer-field{display:grid;gap:7px;color:var(--ink-secondary);font-size:11px;font-weight:700}.drawer-field input,.drawer-field select{width:100%;min-height:44px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;color:var(--ink);background:#fff}.instructor-picker{display:grid;gap:8px}.instructor-option{display:grid!important;grid-template-columns:22px 36px minmax(0,1fr) auto;align-items:center;gap:10px;min-height:58px;padding:9px 11px;border:1px solid var(--line);border-radius:12px;background:#fff;font-weight:400!important;cursor:pointer}.instructor-option:hover{border-color:#9dc1f8}.instructor-option.selected{border-color:#73a8fa;background:var(--blue-soft);box-shadow:0 0 0 2px #e3edff}.instructor-option.bound{cursor:default;background:var(--surface-soft)}.instructor-option input{width:18px!important;height:18px;margin:0;accent-color:var(--blue)}.instructor-option>span:nth-of-type(2){min-width:0}.instructor-option strong,.instructor-option small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.instructor-option strong{color:var(--ink);font-size:12px}.instructor-option small{margin-top:3px;color:var(--muted);font-size:10px}.instructor-option b{padding:5px 7px;border-radius:7px;color:var(--green);background:var(--green-soft);font-size:9px;white-space:nowrap}.drawer-empty{margin:0;padding:18px 12px;border-radius:10px;color:var(--muted);background:var(--surface-soft);font-size:11px;text-align:center}.current-assignments{margin-top:3px;padding-top:15px;border-top:1px solid var(--line)}.current-assignments h3{margin:0 0 4px;color:var(--ink);font-size:13px}.instructor-drawer__footer{display:flex;flex:none;align-items:center;justify-content:space-between;gap:12px;padding:14px 22px calc(14px + env(safe-area-inset-bottom));border-top:1px solid var(--line);background:#fff}.instructor-drawer__footer>span{color:var(--muted);font-size:11px}.instructor-drawer__footer>div{display:flex;gap:8px}.instructor-drawer__footer button{min-height:44px;padding:0 15px}.assignment-list{display:grid;gap:0}.assignment-row{display:flex;align-items:center;gap:10px;padding:12px 0;border-bottom:1px solid var(--line)}.assignment-row>div{flex:1;min-width:0}.assignment-row strong,.assignment-row small{display:block}.assignment-row small{margin-top:3px;color:var(--muted);font-size:10px}.assignment-row select{min-width:110px;min-height:40px;padding:8px;border:1px solid var(--line);border-radius:8px;color:var(--ink);background:#fff}@keyframes drawer-in{from{transform:translateX(24px);opacity:.5}to{transform:none;opacity:1}}@media(max-width:700px){.modal-backdrop:not(.modal-backdrop--drawer){align-items:end;padding:0}.modal-card{width:100%;max-height:92dvh;padding:22px 18px calc(22px + env(safe-area-inset-bottom));border-radius:24px 24px 0 0}}@media(max-width:640px){.modal-backdrop--drawer{align-items:stretch!important}.instructor-drawer{width:100%;border-left:0}.instructor-drawer__header{padding:max(18px,env(safe-area-inset-top)) 18px 14px}.instructor-drawer__body{padding:16px 18px}.instructor-drawer__footer{align-items:stretch;flex-direction:column;padding:12px 18px calc(12px + env(safe-area-inset-bottom))}.instructor-drawer__footer>div{display:grid;grid-template-columns:1fr 1.35fr}.assignment-row{align-items:flex-start;flex-wrap:wrap}.assignment-row select{width:100%}}
</style>
