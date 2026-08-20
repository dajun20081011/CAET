<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/lib/api'

const loading = ref(false)
const groups = ref<any[]>([])
const newName = ref('')

const showDetail = ref(false)
const detail = ref<any | null>(null)
const detailLoading = ref(false)

const showAddMember = ref(false)
const addTarget = ref<any | null>(null)
const availableLearners = ref<any[]>([])
const addLearnerId = ref('')

const showRename = ref(false)
const renameTarget = ref<any | null>(null)
const renameName = ref('')

async function load() {
  loading.value = true
  try {
    groups.value = (await api.groups.list()) || []
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function createGroup() {
  if (!newName.value.trim()) {
    ElMessage.warning('请输入班级名称')
    return
  }
  try {
    await api.groups.create(newName.value.trim())
    newName.value = ''
    ElMessage.success('已创建')
    load()
  } catch (e: any) {
    ElMessage.error(e?.message || '创建失败')
  }
}

async function removeGroup(row: any) {
  try {
    await ElMessageBox.confirm(
      `确认删除班级「${row.name}」？该班级的学员不会被删除，但班级关系会被解除。`,
      '提示',
      { type: 'warning' },
    )
    await api.groups.remove(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e: any) {
    if (e === 'cancel' || e?.type === 'cancel') return
    ElMessage.error(e?.message || '删除失败')
  }
}

function openRename(row: any) {
  renameTarget.value = row
  renameName.value = row.name
  showRename.value = true
}
async function doRename() {
  if (!renameTarget.value || !renameName.value.trim()) return
  try {
    await api.groups.rename(renameTarget.value.id, renameName.value.trim())
    ElMessage.success('已更新')
    showRename.value = false
    load()
  } catch (e: any) {
    ElMessage.error(e?.message || '更新失败')
  }
}

async function openDetail(row: any) {
  showDetail.value = true
  detailLoading.value = true
  detail.value = { id: row.id, name: row.name, learner_count: row.learner_count, learners: [] }
  try {
    detail.value = await api.groups.detail(row.id)
  } catch (e: any) {
    ElMessage.error(e?.message || '加载详情失败')
  } finally {
    detailLoading.value = false
  }
}

async function removeMember(learner: any) {
  if (!detail.value) return
  try {
    await api.groups.removeMember(detail.value.id, learner.id)
    ElMessage.success('已移除')
    openDetail(detail.value)
    load()
  } catch (e: any) {
    ElMessage.error(e?.message || '移除失败')
  }
}

async function openAddMember() {
  if (!detail.value) return
  addTarget.value = detail.value
  showAddMember.value = true
  addLearnerId.value = ''
  try {
    availableLearners.value = (await api.users.list()).filter(
      (u: any) => u.role === 'learner' && u.group_id !== detail.value.id,
    )
  } catch (e: any) {
    ElMessage.error(e?.message || '加载学员列表失败')
  }
}

async function doAddMember() {
  if (!detail.value || !addLearnerId.value) return
  try {
    await api.groups.addMember(detail.value.id, addLearnerId.value)
    ElMessage.success('已添加')
    showAddMember.value = false
    openDetail(detail.value)
    load()
  } catch (e: any) {
    ElMessage.error(e?.message || '添加失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-5">
    <!-- Toolbar -->
    <div class="rounded-xl bg-white border border-gray-100 p-5 flex flex-col md:flex-row md:items-end gap-3">
      <div class="flex-1">
        <p class="text-base font-semibold text-text">班级管理</p>
        <p class="text-xs text-text-secondary mt-1">共 {{ groups.length }} 个班级</p>
      </div>
      <div class="flex gap-2">
        <el-input v-model="newName" placeholder="新班级名称" style="width: 200px" @keyup.enter="createGroup" />
        <el-button type="primary" @click="createGroup">
          <el-icon class="mr-1"><Plus /></el-icon>
          新建
        </el-button>
      </div>
    </div>

    <!-- Table -->
    <div v-loading="loading" class="rounded-xl bg-white border border-gray-100 overflow-hidden">
      <el-table :data="groups" stripe empty-text="暂无班级">
        <el-table-column label="班级名称" min-width="200">
          <template #default="{ row }">
            <span class="font-medium text-text">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="学员数" width="120">
          <template #default="{ row }">
            <el-tag size="small" type="info" effect="plain">{{ row.learner_count }} 人</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="200">
          <template #default="{ row }">
            <span class="text-text-secondary text-xs">
              {{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN', { hour12: false }) : '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">成员</el-button>
            <el-button link type="primary" @click="openRename(row)">重命名</el-button>
            <el-button link type="danger" @click="removeGroup(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Detail dialog -->
    <el-dialog v-model="showDetail" :title="`班级成员 - ${detail?.name || ''}`" width="600">
      <div v-loading="detailLoading">
        <div v-if="detail?.learners?.length" class="space-y-2">
          <div
            v-for="l in detail.learners"
            :key="l.id"
            class="flex items-center justify-between rounded-lg border border-gray-100 px-3 py-2"
          >
            <div>
              <p class="text-sm font-medium text-text">{{ l.display_name || l.email }}</p>
              <p class="text-xs text-text-secondary">{{ l.email }} · {{ l.employee_no || '—' }}</p>
            </div>
            <el-button link type="danger" @click="removeMember(l)">移除</el-button>
          </div>
        </div>
        <p v-else class="text-sm text-text-secondary text-center py-6">本班级暂无学员</p>
      </div>
      <template #footer>
        <el-button @click="showDetail = false">关闭</el-button>
        <el-button type="primary" @click="openAddMember">
          <el-icon class="mr-1"><Plus /></el-icon>
          添加学员
        </el-button>
      </template>
    </el-dialog>

    <!-- Add member dialog -->
    <el-dialog v-model="showAddMember" :title="`为「${addTarget?.name}」添加学员`" width="480">
      <el-select v-model="addLearnerId" placeholder="选择要加入本班的学员" filterable class="w-full">
        <el-option
          v-for="l in availableLearners"
          :key="l.id"
          :label="`${l.display_name || l.email}（${l.email}）`"
          :value="l.id"
        />
      </el-select>
      <p v-if="!availableLearners.length" class="text-xs text-text-secondary mt-2">暂无可加入的学员</p>
      <template #footer>
        <el-button @click="showAddMember = false">取消</el-button>
        <el-button type="primary" :disabled="!addLearnerId" @click="doAddMember">添加</el-button>
      </template>
    </el-dialog>

    <!-- Rename dialog -->
    <el-dialog v-model="showRename" title="重命名班级" width="420">
      <el-input v-model="renameName" />
      <template #footer>
        <el-button @click="showRename = false">取消</el-button>
        <el-button type="primary" @click="doRename">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.text-text { color: #1F2430; }
.text-text-secondary { color: #687280; }
.border-gray-100 { border-color: #F3F4F6; }
.w-full { width: 100%; }
</style>