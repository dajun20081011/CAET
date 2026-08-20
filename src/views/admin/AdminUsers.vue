<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/lib/api'

const loading = ref(false)
const users = ref<any[]>([])
const groups = ref<any[]>([])

const showCreate = ref(false)
const showEdit = ref(false)
const editing = ref<any | null>(null)

const createForm = reactive({
  email: '',
  password: '',
  display_name: '',
  employee_no: '',
  role: 'learner' as 'admin' | 'instructor' | 'learner',
  group_id: '' as string,
})

const editForm = reactive({
  display_name: '',
  employee_no: '',
  role: 'learner' as 'admin' | 'instructor' | 'learner',
  group_id: '' as string,
  is_active: true,
})

const roleMeta: Record<string, { label: string; cls: string }> = {
  admin: { label: '管理员', cls: 'bg-danger/10 text-danger' },
  instructor: { label: '教员', cls: 'bg-warning/10 text-warning' },
  learner: { label: '学员', cls: 'bg-primary-soft text-primary' },
}

async function load() {
  loading.value = true
  try {
    const [u, g] = await Promise.all([api.users.list(), api.groups.list()])
    users.value = u || []
    groups.value = g || []
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(createForm, {
    email: '', password: '', display_name: '', employee_no: '',
    role: 'learner', group_id: '',
  })
  showCreate.value = true
}

async function doCreate() {
  if (!createForm.email || !createForm.password) {
    ElMessage.warning('请填写邮箱与密码')
    return
  }
  try {
    await api.users.create({
      email: createForm.email,
      password: createForm.password,
      display_name: createForm.display_name || undefined,
      employee_no: createForm.employee_no || undefined,
      role: createForm.role,
      group_id: createForm.group_id || undefined,
    })
    ElMessage.success('创建成功')
    showCreate.value = false
    load()
  } catch (e: any) {
    ElMessage.error(e?.message || '创建失败')
  }
}

function openEdit(row: any) {
  editing.value = row
  Object.assign(editForm, {
    display_name: row.display_name || '',
    employee_no: row.employee_no || '',
    role: row.role,
    group_id: row.group_id || '',
    is_active: row.is_active,
  })
  showEdit.value = true
}

async function doEdit() {
  if (!editing.value) return
  try {
    await api.users.update(editing.value.id, {
      display_name: editForm.display_name,
      employee_no: editForm.employee_no,
      role: editForm.role,
      group_id: editForm.group_id || undefined,
      is_active: editForm.is_active,
    })
    ElMessage.success('已更新')
    showEdit.value = false
    load()
  } catch (e: any) {
    ElMessage.error(e?.message || '更新失败')
  }
}

async function toggleActive(row: any) {
  const text = row.is_active ? '禁用' : '启用'
  try {
    await ElMessageBox.confirm(`确认${text}该用户？`, '提示', { type: 'warning' })
    await api.users.update(row.id, { is_active: !row.is_active })
    ElMessage.success(`${text}成功`)
    load()
  } catch (e: any) {
    if (e === 'cancel' || e?.type === 'cancel') return
    ElMessage.error(e?.message || '操作失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-5">
    <div class="rounded-xl bg-white border border-gray-100 p-5 flex items-center justify-between">
      <div>
        <h2 class="text-base font-semibold text-text">用户管理</h2>
        <p class="text-xs text-text-secondary mt-1">共 {{ users.length }} 个账号</p>
      </div>
      <el-button type="primary" @click="openCreate">
        <el-icon class="mr-1"><Plus /></el-icon>
        新建用户
      </el-button>
    </div>

    <div v-loading="loading" class="rounded-xl bg-white border border-gray-100 overflow-hidden">
      <el-table :data="users" stripe empty-text="暂无用户">
        <el-table-column label="账号" min-width="220">
          <template #default="{ row }">
            <p class="font-medium text-text">{{ row.display_name || row.email }}</p>
            <p class="text-xs text-text-secondary">{{ row.email }}</p>
          </template>
        </el-table-column>
        <el-table-column label="工号" prop="employee_no" width="120">
          <template #default="{ row }">{{ row.employee_no || '—' }}</template>
        </el-table-column>
        <el-table-column label="角色" width="120">
          <template #default="{ row }">
            <span class="px-2 py-0.5 rounded text-xs" :class="roleMeta[row.role]?.cls || 'bg-gray-100 text-text-secondary'">
              {{ roleMeta[row.role]?.label || row.role }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="班级" prop="group_name" min-width="140">
          <template #default="{ row }">{{ row.group_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.is_active" type="success" size="small">启用</el-tag>
            <el-tag v-else type="info" size="small">禁用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link :type="row.is_active ? 'danger' : 'success'" @click="toggleActive(row)">
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Create dialog -->
    <el-dialog v-model="showCreate" title="新建用户" width="480">
      <el-form label-position="top">
        <el-form-item label="邮箱" required>
          <el-input v-model="createForm.email" placeholder="user@example.com" />
        </el-form-item>
        <el-form-item label="初始密码" required>
          <el-input v-model="createForm.password" type="password" placeholder="至少 8 位" show-password />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="createForm.display_name" />
        </el-form-item>
        <el-form-item label="工号">
          <el-input v-model="createForm.employee_no" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="createForm.role" class="w-full">
            <el-option label="学员" value="learner" />
            <el-option label="教员" value="instructor" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
        <el-form-item label="班级（仅学员）">
          <el-select v-model="createForm.group_id" placeholder="无" clearable class="w-full">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="doCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- Edit dialog -->
    <el-dialog v-model="showEdit" title="编辑用户" width="480">
      <el-form label-position="top" v-if="editing">
        <el-form-item label="邮箱">
          <el-input :model-value="editing.email" disabled />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="editForm.display_name" />
        </el-form-item>
        <el-form-item label="工号">
          <el-input v-model="editForm.employee_no" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="editForm.role" class="w-full">
            <el-option label="学员" value="learner" />
            <el-option label="教员" value="instructor" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
        <el-form-item label="班级">
          <el-select v-model="editForm.group_id" placeholder="无" clearable class="w-full">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="editForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" @click="doEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.bg-primary-soft { background-color: #F3EDFF; }
.text-primary { color: #7C3AED; }
.text-text { color: #1F2430; }
.text-text-secondary { color: #687280; }
.text-danger { color: #EF4444; }
.text-warning { color: #F59E0B; }
.bg-gray-100 { background-color: #F3F4F6; }
.border-gray-100 { border-color: #F3F4F6; }
.w-full { width: 100%; }
</style>