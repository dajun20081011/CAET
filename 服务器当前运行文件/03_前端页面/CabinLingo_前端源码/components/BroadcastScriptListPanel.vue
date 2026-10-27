<template>
  <section class="panel script-list-panel">
    <div class="panel__heading">
      <div><h2>广播词列表</h2><p>完成正文和切片后可启用；任务发布只能选择已启用广播词</p></div>
      <button class="primary-button primary-button--compact" type="button" @click="$emit('create')">+ 新建广播词</button>
    </div>
    <form class="script-filters" @submit.prevent="search">
      <label><span>搜索</span><input v-model.trim="filters.keyword" placeholder="名称或类型"></label>
      <label><span>语言</span><select v-model="filters.language"><option value="">全部语言</option><option value="zh_cn">中文</option><option value="en_us">英文</option></select></label>
      <label><span>类型</span><select v-model="filters.script_type"><option value="">全部类型</option><option v-for="item in BROADCAST_SCRIPT_TYPE_OPTIONS" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
      <label><span>所属公司</span><select v-model="filters.company_id"><option value="">全部公司</option><option v-for="org in organizations" :key="org.id" :value="org.id">{{ org.name }}</option></select></label>
      <label><span>使用状态</span><select v-model="filters.enabled"><option value="">全部</option><option value="true">已启用</option><option value="false">未启用</option></select></label>
      <button class="outline-button" type="submit">查询</button>
    </form>
    <div class="script-table" role="table" aria-label="广播词列表">
      <div class="script-row script-row--head" role="row"><span>广播词名称</span><span>类型 / 语言</span><span>所属公司</span><span>切片</span><span>状态</span><span>操作</span></div>
      <div v-for="item in page.items" :key="item.id" class="script-row" role="row">
        <button class="script-title" type="button" @click="$emit('open', item)"><strong>{{ item.title }}</strong><small>更新于 {{ formatDate(item.updated_at) }}</small></button>
        <span><strong>{{ broadcastScriptTypeLabel(item.script_type) }}</strong><small>{{ languageLabel(item.language) }}</small></span>
        <span>{{ item.company_name || '全平台公共' }}</span>
        <span><strong>{{ item.slice_count }} 段</strong><small>{{ item.ready ? '内容已完成' : '待完成保存' }}</small></span>
        <span><i class="status-chip" :class="item.enabled ? 'enabled' : item.ready ? 'disabled' : 'incomplete'">{{ item.enabled ? '已启用' : item.ready ? '已停用' : '未完成' }}</i></span>
        <span class="row-actions">
          <button class="outline-button outline-button--small" type="button" @click="$emit('open', item)">编辑内容</button>
          <button class="outline-button outline-button--small" :class="{ danger: item.enabled }" type="button" :disabled="!item.ready && !item.enabled" :title="!item.ready && !item.enabled ? '请先完成正文和切片' : ''" :aria-pressed="item.enabled" @click="$emit('toggle', item)">{{ item.enabled ? '停用' : '启用' }}</button>
        </span>
      </div>
      <div v-if="!page.items.length" class="empty-panel">没有符合条件的广播词</div>
    </div>
    <footer v-if="page.total > page.page_size" class="pagination"><span>共 {{ page.total }} 条</span><button class="outline-button outline-button--small" :disabled="page.page <= 1" @click="$emit('page', page.page - 1)">上一页</button><button class="outline-button outline-button--small" :disabled="page.page * page.page_size >= page.total" @click="$emit('page', page.page + 1)">下一页</button></footer>
  </section>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import type { BroadcastScript, BroadcastScriptPage, Organization } from '@/api'
import { BROADCAST_SCRIPT_TYPE_OPTIONS, broadcastScriptTypeLabel } from '@/domain/broadcastScripts'

defineProps<{ page: BroadcastScriptPage; organizations: Organization[] }>()
const emit = defineEmits<{
  search: [filters: { keyword?: string; language?: string; script_type?: string; company_id?: string; enabled?: boolean; archived: false; page: number }]
  create: []; open: [script: BroadcastScript]; toggle: [script: BroadcastScript]; page: [page: number]
}>()
const filters = reactive({ keyword: '', language: '', script_type: '', company_id: '', enabled: '' })
function search() {
  emit('search', {
    keyword: filters.keyword || undefined, language: filters.language || undefined,
    script_type: filters.script_type || undefined, company_id: filters.company_id || undefined,
    enabled: filters.enabled === '' ? undefined : filters.enabled === 'true', archived: false, page: 1,
  })
}
function languageLabel(value: string) { return value === 'zh_cn' ? '中文' : value === 'en_us' ? '英文' : value }
function formatDate(value: string) { return new Date(value).toLocaleDateString('zh-CN') }
</script>

<style scoped>
.script-list-panel{min-height:560px}.script-filters{display:grid;grid-template-columns:1.4fr repeat(4,minmax(120px,.8fr)) auto;gap:10px;align-items:end;margin:18px 0}.script-filters label{display:grid;gap:6px;color:var(--muted);font-size:11px}.script-filters input,.script-filters select{width:100%;min-height:42px;padding:9px 10px;border:1px solid var(--line);border-radius:10px;color:var(--ink);background:#fff}.script-row{display:grid;grid-template-columns:minmax(190px,1.5fr) minmax(120px,.8fr) minmax(130px,.9fr) 100px 90px minmax(190px,1fr);gap:12px;align-items:center;padding:14px 10px;border-top:1px solid var(--line);font-size:12px}.script-row--head{color:var(--muted);background:var(--surface-soft);font-size:11px}.script-row strong,.script-row small{display:block}.script-row small{margin-top:4px;color:var(--muted);font-size:10px}.script-title{border:0;color:var(--ink);background:none;text-align:left}.script-title strong{font-size:14px}.row-actions{display:flex;gap:7px}.outline-button--small{min-height:36px;padding:7px 10px;font-size:11px}.outline-button--small.danger{color:#bd4c5d;border-color:#efbdc5}.status-chip{display:inline-flex;padding:5px 9px;border-radius:999px;font-style:normal}.status-chip.enabled{color:#177553;background:#e6f8f0}.status-chip.disabled{color:#526787;background:#edf2f8}.status-chip.incomplete{color:#aa681e;background:#fff4e4}.pagination{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-top:16px;color:var(--muted);font-size:11px}@media(max-width:1120px){.script-filters{grid-template-columns:repeat(3,1fr)}.script-table{overflow:auto}.script-row{min-width:900px}}@media(max-width:700px){.script-filters{grid-template-columns:1fr 1fr}.script-filters button{grid-column:1/-1}.panel__heading{gap:12px}.panel__heading .primary-button{width:100%}}
</style>
