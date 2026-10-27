<template>
  <section class="class-management">
    <aside class="scope-panel">
      <div class="section-heading">
        <div><p class="page-kicker">ORGANIZATION</p><h2>选择组织</h2><p>班级与学员归属于组织数据范围。</p></div>
        <span>{{ organizations.length }}</span>
      </div>
      <div class="organization-list">
        <button v-for="item in organizations" :key="item.id" type="button" :class="{ selected: selectedOrganizationId === item.id }" @click="selectOrganization(item.id)">
          <span><strong>{{ item.name }}</strong><small>{{ item.code }}</small></span>
          <b>{{ item.class_count }} 个班级</b>
        </button>
        <div v-if="!organizations.length" class="empty-state"><strong>暂无组织</strong><p>请先点击上方“新建组织”。</p></div>
      </div>
    </aside>

    <section class="directory-panel">
      <div class="section-heading directory-heading">
        <div><p class="page-kicker">CLASS DIRECTORY</p><h2>{{ selectedOrganization?.name || '班级目录' }}</h2><p>训练班接收练习，考核班接收考试；成员可加入多个班级。</p></div>
        <button class="primary-button primary-button--compact" type="button" :aria-disabled="!organizations.length" @click="openCreate">+ 新建班级</button>
      </div>

      <p v-if="pageError" class="directory-error" role="alert">{{ pageError }}</p>

      <div class="class-summary" aria-label="班级统计">
        <button v-for="item in classFilters" :key="item.value" type="button" :class="{ active: typeFilter === item.value }" @click="typeFilter = item.value">
          <strong>{{ item.count }}</strong><span>{{ item.label }}</span>
        </button>
      </div>

      <div v-if="visibleClasses.length" class="class-list">
        <article v-for="item in visibleClasses" :key="item.id" class="class-card">
          <button type="button" class="class-card__main" @click="openDetail(item)">
            <span class="class-type" :class="item.class_type">{{ classTypeLabel(item.class_type) }}</span>
            <span class="class-copy"><strong>{{ item.name }}</strong><small>{{ item.code }}<template v-if="item.start_date"> · {{ item.start_date }} 至 {{ item.end_date || '长期' }}</template></small></span>
          </button>
          <div class="class-members"><strong>{{ item.member_count }}</strong><span>名学员</span></div>
          <span class="state-pill" :class="item.status">{{ item.status === 'active' ? '启用' : '已停用' }}</span>
          <div class="class-actions">
            <button type="button" @click="openDetail(item)">成员</button>
            <button type="button" @click="openEdit(item)">编辑</button>
            <button v-if="item.status === 'active'" type="button" class="danger" @click="changeStatus(item, 'inactive')">停用</button>
            <button v-else type="button" class="success" @click="changeStatus(item, 'active')">启用</button>
          </div>
        </article>
      </div>
      <div v-else class="empty-state empty-state--large"><strong>{{ filteredClasses.length ? '当前筛选下没有班级' : '当前组织还没有班级' }}</strong><p>{{ filteredClasses.length ? '切换上方班级类型查看。' : '新建班级后，可批量添加学员并按班级发布任务。' }}</p></div>
    </section>

    <Teleport to="body">
      <div v-if="dialog === 'class'" class="class-modal-backdrop" role="presentation" @click.self="closeDialog">
        <form class="class-modal" role="dialog" aria-modal="true" :aria-label="editingClass ? '编辑班级' : '新建班级'" @submit.prevent="saveClass">
          <header class="modal-heading"><div><h2>{{ editingClass ? '编辑班级' : '新建班级' }}</h2><p>选择班级类型后，只接收对应类型的任务。</p></div><button type="button" aria-label="关闭" @click="closeDialog">×</button></header>
          <div class="form-grid">
            <label>班级编码<input v-model.trim="classForm.code" required maxlength="80" placeholder="如 TRAIN-2026-01"></label>
            <label>班级名称<input v-model.trim="classForm.name" required maxlength="200" placeholder="如 2026年广播训练班"></label>
            <label class="full-field">班级类型<select v-model="classForm.class_type"><option value="training">训练班 · 接收练习任务</option><option value="assessment">考核班 · 接收考试任务</option></select></label>
            <label>开始日期<input v-model="classForm.start_date" type="date"></label>
            <label>结束日期<input v-model="classForm.end_date" type="date"></label>
            <label class="full-field">备注<textarea v-model.trim="classForm.description" rows="3" maxlength="4000" placeholder="可填写培训批次、用途等"></textarea></label>
          </div>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <footer class="modal-actions"><button type="button" class="cancel" :disabled="busy" @click="closeDialog">取消</button><button type="submit" class="save" :disabled="busy">{{ busy ? '保存中…' : '保存班级' }}</button></footer>
        </form>
      </div>

      <div v-if="detail" class="class-modal-backdrop" role="presentation" @click.self="closeDetail">
        <section class="class-modal class-detail" role="dialog" aria-modal="true" aria-label="班级成员管理">
          <header class="modal-heading"><div><p class="page-kicker">CLASS MEMBERS</p><h2>{{ detail.name }}</h2><p>{{ classTypeLabel(detail.class_type) }} · {{ detail.status === 'active' ? '启用' : '已停用' }} · {{ detail.member_count }} 名学员</p></div><button type="button" aria-label="关闭" @click="closeDetail">×</button></header>
          <div class="class-meta"><span>{{ detail.code }}</span><span v-if="detail.start_date">{{ detail.start_date }} 至 {{ detail.end_date || '长期' }}</span><span>{{ detail.description || '暂无备注' }}</span></div>
          <div class="member-add">
            <label><span>添加学员</span><select v-model="selectedStudentIds" multiple size="4" aria-label="选择要添加的学员"><option v-for="student in availableStudents" :key="student.id" :value="student.id">{{ student.display_name }} · {{ student.external_ref || '无工号' }}</option></select></label>
            <button type="button" :disabled="!selectedStudentIds.length || busy" @click="addStudents">添加选中学员</button>
          </div>
          <div class="member-list">
            <article v-for="member in detail.members" :key="member.id">
              <div class="member-avatar">{{ member.display_name.slice(0, 1) }}</div>
              <div><strong>{{ member.display_name }} <small>{{ member.employee_no || '无工号' }}</small></strong><span>训练教员：{{ member.training_instructors.join('、') || '未绑定' }}</span><span>考核教员：{{ member.assessment_instructors.join('、') || '未绑定' }}</span></div>
              <button type="button" :disabled="busy" @click="removeStudent(member)">移除</button>
            </article>
            <div v-if="!detail.members.length" class="empty-state"><strong>班级暂无学员</strong><p>从上方选择学员后批量添加。</p></div>
          </div>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        </section>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { cabinlingoApi, type ClassDetail, type Organization, type TrainingClass, type UserSummary } from '@/api'

const props = defineProps<{ organizations: Organization[]; classes: TrainingClass[]; users: UserSummary[]; selectedOrganizationId?: string }>()
const emit = defineEmits<{ changed: []; 'update:selectedOrganizationId': [value: string] }>()
const selectedOrganizationId = ref(props.selectedOrganizationId || props.organizations[0]?.id || '')
const typeFilter = ref<'all' | 'training' | 'assessment'>('all')
const dialog = ref<'class' | null>(null)
const detail = ref<ClassDetail | null>(null)
const editingClass = ref<TrainingClass | null>(null)
const busy = ref(false)
const error = ref('')
const pageError = ref('')
const selectedStudentIds = ref<string[]>([])
const classForm = ref({ code: '', name: '', class_type: 'training' as 'training' | 'assessment', description: '', start_date: '', end_date: '' })

const selectedOrganization = computed(() => props.organizations.find(item => item.id === selectedOrganizationId.value))
const filteredClasses = computed(() => props.classes.filter(item => item.organization_id === selectedOrganizationId.value))
const visibleClasses = computed(() => filteredClasses.value.filter(item => typeFilter.value === 'all' || item.class_type === typeFilter.value))
const classFilters = computed(() => [
  { value: 'all' as const, label: '全部班级', count: filteredClasses.value.length },
  { value: 'training' as const, label: '训练班', count: filteredClasses.value.filter(item => item.class_type === 'training').length },
  { value: 'assessment' as const, label: '考核班', count: filteredClasses.value.filter(item => item.class_type === 'assessment').length },
])
const learnerUsers = computed(() => props.users.filter(user => user.roles.includes('learner') && user.is_active))
const memberIds = computed(() => new Set(detail.value?.members.map(member => member.id) || []))
const availableStudents = computed(() => learnerUsers.value.filter(student => !memberIds.value.has(student.id)))

watch(() => props.selectedOrganizationId, value => { if (value && props.organizations.some(item => item.id === value)) selectedOrganizationId.value = value })
watch(() => props.organizations, value => {
  if (!value.some(item => item.id === selectedOrganizationId.value)) selectedOrganizationId.value = value[0]?.id || ''
}, { deep: true, immediate: true })
watch(selectedOrganizationId, value => { typeFilter.value = 'all'; pageError.value = ''; emit('update:selectedOrganizationId', value) })

function classTypeLabel(type: string) { return type === 'assessment' ? '考核班' : '训练班' }
function selectOrganization(id: string) { selectedOrganizationId.value = id }
function openCreate() {
  const organizationId = selectedOrganizationId.value || props.selectedOrganizationId || props.organizations[0]?.id || ''
  if (!organizationId) { pageError.value = '请先新建组织，再创建班级。'; return }
  selectedOrganizationId.value = organizationId
  editingClass.value = null
  classForm.value = { code: '', name: '', class_type: 'training', description: '', start_date: '', end_date: '' }
  error.value = ''
  pageError.value = ''
  dialog.value = 'class'
}
function openEdit(item: TrainingClass) { editingClass.value = item; classForm.value = { code: item.code, name: item.name, class_type: item.class_type, description: item.description || '', start_date: item.start_date || '', end_date: item.end_date || '' }; error.value = ''; dialog.value = 'class' }
function closeDialog() { dialog.value = null; busy.value = false; error.value = '' }
async function saveClass() {
  if (!editingClass.value && !selectedOrganizationId.value) { error.value = '未选择组织，请关闭窗口后选择组织再试。'; return }
  if (classForm.value.start_date && classForm.value.end_date && classForm.value.end_date < classForm.value.start_date) { error.value = '结束日期不能早于开始日期。'; return }
  busy.value = true; error.value = ''
  try {
    const payload = { ...classForm.value, start_date: classForm.value.start_date || null, end_date: classForm.value.end_date || null }
    if (editingClass.value) await cabinlingoApi.updateClass(editingClass.value.id, payload)
    else await cabinlingoApi.createClass({ organization_id: selectedOrganizationId.value, ...payload })
    closeDialog(); emit('changed')
  } catch (caught) {
    const detail = (caught as { response?: { data?: { detail?: string } } }).response?.data?.detail || ''
    error.value = detail.includes('already exists') ? '当前组织内已存在相同班级编码，请更换编码。' : detail || '保存失败，请检查日期与必填项后重试。'
    busy.value = false
  }
}
async function changeStatus(item: TrainingClass, status: 'active' | 'inactive') {
  const verb = status === 'active' ? '启用' : '停用'
  if (!window.confirm(`确认${verb}“${item.name}”？${status === 'inactive' ? '历史任务和成员记录仍会保留。' : ''}`)) return
  busy.value = true
  try { await cabinlingoApi.updateClass(item.id, { status }); emit('changed') } catch { error.value = `${verb}失败，请稍后重试。` } finally { busy.value = false }
}
async function openDetail(item: TrainingClass) { error.value = ''; try { detail.value = await cabinlingoApi.classDetail(item.id); selectedStudentIds.value = [] } catch { error.value = '班级详情加载失败，请刷新后重试。' } }
function closeDetail() { detail.value = null; selectedStudentIds.value = []; error.value = '' }
async function addStudents() { if (!detail.value || !selectedStudentIds.value.length) return; busy.value = true; error.value = ''; try { await cabinlingoApi.addClassStudents(detail.value.id, selectedStudentIds.value); detail.value = await cabinlingoApi.classDetail(detail.value.id); selectedStudentIds.value = []; emit('changed') } catch { error.value = '添加学员失败，请只选择有效的学员账号。' } finally { busy.value = false } }
async function removeStudent(member: { id: string; display_name: string }) { if (!detail.value || !window.confirm(`确认从班级移除“${member.display_name}”？`)) return; busy.value = true; try { await cabinlingoApi.removeClassStudent(detail.value.id, member.id); detail.value = await cabinlingoApi.classDetail(detail.value.id); emit('changed') } catch { error.value = '移除失败，请稍后重试。' } finally { busy.value = false } }
</script>

<style scoped>
.class-management{display:grid;grid-template-columns:minmax(260px,.68fr) minmax(560px,1.65fr);gap:20px}.scope-panel,.directory-panel{min-width:0;padding:23px;border:1px solid #e5edf8;border-radius:18px;background:#fff;box-shadow:var(--shadow-card)}.section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:18px}.section-heading h2{margin:0;color:var(--ink);font-size:18px}.section-heading p:not(.page-kicker){margin:6px 0 0;color:var(--muted);font-size:11px;line-height:1.6}.page-kicker{margin:0 0 5px;color:var(--blue);font-size:9px;font-weight:800;letter-spacing:.14em}.section-heading>span{display:grid;place-items:center;min-width:34px;height:34px;border-radius:10px;color:var(--blue);background:var(--blue-soft);font-weight:800}.directory-heading button{min-height:44px}.organization-list{display:grid;gap:8px}.organization-list button{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;min-height:64px;padding:12px;border:1px solid transparent;border-radius:12px;color:var(--ink);background:var(--surface-soft);text-align:left}.organization-list button:hover{border-color:#bed5fa}.organization-list button.selected{border-color:#8ebaff;background:var(--blue-soft);box-shadow:0 0 0 2px #dfebff}.organization-list strong,.organization-list small{display:block}.organization-list small{margin-top:5px;color:var(--muted);font-size:10px}.organization-list b{color:var(--blue);font-size:10px;white-space:nowrap}.class-summary{display:flex;gap:8px;margin-bottom:10px}.class-summary button{display:flex;align-items:center;gap:8px;min-height:42px;padding:8px 13px;border:1px solid var(--line);border-radius:10px;color:var(--muted);background:#fff}.class-summary button.active{color:var(--blue);border-color:#9cc2ff;background:var(--blue-soft)}.class-summary strong{font-size:16px}.class-summary span{font-size:10px}.class-list{display:grid}.class-card{display:grid;grid-template-columns:minmax(240px,1fr) 72px 74px auto;align-items:center;gap:16px;padding:17px 0;border-top:1px solid var(--line)}.class-card__main{display:flex;align-items:center;gap:12px;min-width:0;color:var(--ink);background:transparent;text-align:left}.class-type{display:grid;place-items:center;flex:none;width:50px;height:38px;border-radius:10px;color:var(--blue);background:var(--blue-soft);font-size:10px;font-weight:700}.class-type.assessment{color:var(--green);background:var(--green-soft)}.class-copy{min-width:0}.class-copy strong,.class-copy small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.class-copy strong{font-size:13px}.class-copy small{margin-top:5px;color:var(--muted);font-size:10px}.class-members{text-align:center}.class-members strong,.class-members span{display:block}.class-members strong{font-size:18px}.class-members span{color:var(--muted);font-size:9px}.state-pill{padding:6px 9px;border-radius:999px;font-size:10px;font-weight:700;text-align:center}.state-pill.active{color:var(--green);background:var(--green-soft)}.state-pill.inactive{color:var(--muted);background:#edf2f8}.class-actions{display:flex;gap:6px}.class-actions button{min-height:38px;padding:0 10px;border:1px solid #c4d8f8;border-radius:8px;color:var(--blue);background:#fff;font-size:10px}.class-actions button.danger{color:var(--red);border-color:#f0c5cc}.class-actions button.success{color:var(--green);border-color:#afe1d0}.empty-state{padding:30px 14px;text-align:center}.empty-state strong{color:var(--ink)}.empty-state p{margin:7px 0 0;color:var(--muted);font-size:11px}.empty-state--large{padding:70px 20px}
.directory-error{margin:-4px 0 14px;padding:10px 12px;border-radius:10px;color:#a84040;background:#fff0f0;font-size:11px}.class-modal-backdrop{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:24px;background:#061b456b;backdrop-filter:blur(4px)}.class-modal{width:min(620px,100%);max-height:90vh;overflow:auto;padding:26px;border:1px solid #e6edf7;border-radius:20px;background:#fff;box-shadow:0 28px 90px #08204d4d}.class-detail{width:min(800px,100%)}.modal-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:20px}.modal-heading h2{margin:0;color:var(--ink);font-size:21px}.modal-heading p:not(.page-kicker){margin:6px 0 0;color:var(--muted);font-size:12px}.modal-heading>button{display:grid;place-items:center;flex:none;width:44px;height:44px;border-radius:50%;color:#647696;background:#f1f5fb;font-size:24px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}.form-grid label,.member-add label{display:grid;gap:7px;color:var(--ink-secondary);font-size:11px;font-weight:700}.form-grid input,.form-grid select,.form-grid textarea,.member-add select{width:100%;min-height:44px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;color:var(--ink);background:#fff}.full-field{grid-column:1/-1}.form-error{margin:14px 0 0;padding:10px 12px;border-radius:9px;color:#b14355;background:var(--red-soft);font-size:11px}.modal-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:20px;padding-top:16px;border-top:1px solid var(--line)}.modal-actions button{min-width:92px;min-height:44px;border-radius:10px}.modal-actions .cancel{color:var(--blue);border:1px solid #bed4f8;background:#fff}.modal-actions .save{color:#fff;background:var(--blue)}.class-meta{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px}.class-meta span{padding:7px 10px;border-radius:8px;color:var(--ink-secondary);background:var(--surface-soft);font-size:10px}.member-add{display:grid;grid-template-columns:1fr auto;align-items:end;gap:12px;padding:16px;border-radius:13px;background:var(--surface-soft)}.member-add select{min-height:92px}.member-add>button{min-height:44px;padding:0 14px;border-radius:9px;color:#fff;background:var(--blue)}.member-add>button:disabled{opacity:.55}.member-list{display:grid;margin-top:12px}.member-list article{display:grid;grid-template-columns:38px 1fr auto;align-items:center;gap:12px;padding:13px 2px;border-bottom:1px solid var(--line)}.member-avatar{display:grid;place-items:center;width:36px;height:36px;border-radius:50%;color:#fff;background:linear-gradient(135deg,var(--blue),var(--navy))}.member-list article strong,.member-list article span{display:block}.member-list article strong{font-size:12px}.member-list article strong small{margin-left:6px;color:var(--muted);font-size:9px;font-weight:400}.member-list article span{margin-top:4px;color:var(--muted);font-size:10px}.member-list article>button{min-height:38px;padding:0 10px;border:1px solid #f0c5cc;border-radius:8px;color:var(--red);background:#fff;font-size:10px}
@media(max-width:1050px){.class-management{grid-template-columns:1fr}.organization-list{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:720px){.scope-panel,.directory-panel{padding:17px}.organization-list{grid-template-columns:1fr}.directory-heading{flex-direction:column}.directory-heading button{width:100%}.class-summary{overflow:auto}.class-summary button{flex:none}.class-card{grid-template-columns:1fr 64px}.class-card>.state-pill{justify-self:end}.class-members{display:none}.class-actions{grid-column:1/-1;justify-content:flex-end}.class-actions button{min-height:44px;flex:1}.class-modal-backdrop{align-items:end;padding:0}.class-modal{width:100%;max-height:94vh;padding:22px 18px calc(22px + env(safe-area-inset-bottom));border-radius:24px 24px 0 0}.form-grid{grid-template-columns:1fr}.full-field{grid-column:auto}.modal-actions{position:sticky;bottom:0;margin:18px -18px -22px;padding:14px 18px calc(14px + env(safe-area-inset-bottom));background:#fff}.modal-actions button{flex:1}.member-add{grid-template-columns:1fr}.member-list article{grid-template-columns:36px 1fr}.member-list article>button{grid-column:2;justify-self:start;min-width:82px}}
</style>
