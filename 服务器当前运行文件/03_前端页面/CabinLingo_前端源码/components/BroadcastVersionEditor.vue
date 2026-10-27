<template>
  <section class="script-editor">
    <button class="back-link" type="button" @click="$emit('back')"><AppIcon name="back" /> 返回广播词列表</button>
    <section class="panel editor-hero">
      <div><p class="portal-kicker">Broadcast Standard Asset</p><h2>{{ script.title }}</h2><p>{{ script.company_name || '全平台公共' }} · {{ broadcastScriptTypeLabel(script.script_type) }} · {{ languageLabel(script.language) }}</p></div>
      <span class="edit-state">{{ script.enabled ? '当前已启用；修改内容后自动停用' : '内容编辑' }}</span>
    </section>

    <section class="panel metadata-panel">
      <div class="panel__heading"><div><h2>基本信息</h2><p>保留任务发布所需的广播词属性</p></div><button class="outline-button" :disabled="saving || readOnly" @click="saveMetadata">保存信息</button></div>
      <div class="metadata-grid">
        <label><span>广播词名称</span><input v-model.trim="metadata.title" maxlength="160" :disabled="readOnly" @blur="syncMetadataTitleLanguageSuffix"></label>
        <label><span>语言</span><select v-model="metadata.language" :disabled="readOnly" @change="syncMetadataTitleLanguageSuffix"><option value="zh_cn">中文 zh_cn</option><option value="en_us">英文 en_us</option></select></label>
        <label><span>广播词类型</span><select v-model="metadata.script_type" :disabled="readOnly"><option v-for="item in BROADCAST_SCRIPT_TYPE_OPTIONS" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
        <label><span>所属公司</span><select v-model="metadata.company_id" :disabled="readOnly"><option value="">全平台公共</option><option v-for="org in organizations" :key="org.id" :value="org.id">{{ org.name }}</option></select></label>
      </div>
    </section>

    <section class="panel content-panel">
      <div class="step-heading"><span>1</span><div><h2>输入完整正文</h2><p>点击保存后自动切片，已有切片将按新正文重新生成</p></div></div>
      <textarea class="full-text" :value="fullText" rows="13" maxlength="500000" :readonly="readOnly" :disabled="saving" aria-label="完整标准正文" @input="updateFullText" />
      <div class="text-meta"><span>{{ fullText.length }} 字符</span><span v-if="hasUnsavedText" class="pending-text">尚未保存</span></div>
      <div v-if="!readOnly" class="editor-actions"><button class="primary-button primary-button--compact" :disabled="saving || !fullText.trim()" @click="$emit('save-and-generate')">{{ saving ? '处理中…' : '保存正文并自动切片' }}</button></div>

      <div class="step-heading step-heading--slices"><span>2</span><div><h2>调整切片并完成</h2><p>可直接改文字、增删或调整顺序；所有切片必须与完整正文一致</p></div></div>
      <BroadcastSliceList :slices="slices" :frozen="readOnly" :saving="saving" @update="(slice, changes) => $emit('update-slice', slice, changes)" @remove="slice => $emit('remove-slice', slice)" @move="(index, direction) => $emit('move-slice', index, direction)" @add="payload => $emit('add-slice', payload)" />
      <div v-if="!readOnly" class="complete-bar" :class="{ ready: canComplete }"><p>{{ completionText }}</p><button class="primary-button primary-button--compact" :disabled="!canComplete" @click="$emit('complete')">完成保存</button></div>
      <p v-else class="readonly-note"><AppIcon name="lock" /> 该历史内容为只读状态。</p>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { BroadcastScript, BroadcastSlice, BroadcastVersion, Organization } from '@/api'
import AppIcon from '@/components/AppIcon.vue'
import BroadcastSliceList from '@/components/BroadcastSliceList.vue'
import { BROADCAST_SCRIPT_TYPE_OPTIONS, broadcastScriptTypeLabel, normalizeBroadcastScriptType, withBroadcastLanguageSuffix } from '@/domain/broadcastScripts'

const props = defineProps<{ script: BroadcastScript; version: BroadcastVersion; slices: BroadcastSlice[]; organizations: Organization[]; fullText: string; saving: boolean }>()
const emit = defineEmits<{
  back: []; 'save-meta': [payload: { title: string; language: string; script_type: string; company_id: string | null }]
  'update:fullText': [value: string]; 'save-and-generate': []; complete: []
  'update-slice': [slice: BroadcastSlice, changes: { text?: string }]
  'remove-slice': [slice: BroadcastSlice]; 'move-slice': [index: number, direction: -1 | 1]
  'add-slice': [payload: { text: string; verified: boolean }]
}>()
const metadata = reactive({ title: '', language: 'zh_cn', script_type: '', company_id: '' })
const readOnly = computed(() => props.version.frozen || props.script.status === 'archived')
const hasUnsavedText = computed(() => props.fullText !== props.version.full_text)
const slicesMatchText = computed(() => props.slices.length > 0 && props.slices.map(item => item.text).join('') === props.fullText)
const canComplete = computed(() => !props.saving && !readOnly.value && !hasUnsavedText.value && !props.version.slices_stale && slicesMatchText.value)
const completionText = computed(() => canComplete.value ? '正文与切片已一致，可完成保存。' : hasUnsavedText.value ? '请先保存正文并自动切片。' : !props.slices.length ? '还没有切片。' : '切片与正文不一致，请继续调整。')
watch(() => props.script, script => Object.assign(metadata, { title: script.title, language: script.language, script_type: normalizeBroadcastScriptType(script.script_type), company_id: script.company_id || '' }), { immediate: true })
function updateFullText(event: Event) { emit('update:fullText', (event.target as HTMLTextAreaElement).value) }
function syncMetadataTitleLanguageSuffix() { metadata.title = withBroadcastLanguageSuffix(metadata.title, metadata.language) }
function saveMetadata() { syncMetadataTitleLanguageSuffix(); emit('save-meta', { title: metadata.title, language: metadata.language, script_type: metadata.script_type, company_id: metadata.company_id || null }) }
function languageLabel(value: string) { return value === 'zh_cn' ? '中文' : value === 'en_us' ? '英文' : value }
</script>

<style scoped>
.script-editor{display:grid;gap:16px}.back-link{width:max-content;display:flex;align-items:center;gap:7px;border:0;color:var(--blue);background:none;font-weight:700}.editor-hero{display:flex;align-items:center;justify-content:space-between;gap:20px;background:linear-gradient(135deg,#fff,#f4f8ff)}.editor-hero h2{margin:5px 0;color:var(--ink);font-size:25px}.editor-hero>div>p:last-child{margin:0;color:var(--muted);font-size:12px}.edit-state{padding:8px 12px;border-radius:999px;color:#526787;background:#edf2f8;font-size:11px;font-weight:700}.metadata-grid{display:grid;grid-template-columns:1.4fr .7fr 1fr 1fr;gap:12px}.metadata-grid label{display:grid;gap:6px;color:var(--muted);font-size:11px}.metadata-grid input,.metadata-grid select{width:100%;min-height:42px;padding:9px 10px;border:1px solid var(--line);border-radius:10px;color:var(--ink);background:#fff}.step-heading{display:flex;align-items:center;gap:10px;margin-bottom:12px}.step-heading>span{display:grid;place-items:center;width:30px;height:30px;border-radius:50%;color:#fff;background:var(--blue);font-weight:800}.step-heading h2{margin:0;color:var(--ink);font-size:17px}.step-heading p{margin:3px 0 0;color:var(--muted);font-size:11px}.step-heading--slices{margin-top:28px}.full-text{width:100%;padding:15px;border:1px solid #cfdbec;border-radius:13px;color:var(--ink);background:#fff;line-height:1.8;resize:vertical}.full-text[readonly]{background:#f5f7fa}.text-meta{display:flex;justify-content:space-between;gap:12px;margin-top:8px;color:var(--muted);font-size:11px}.pending-text{color:#b3651b;font-weight:700}.editor-actions{display:flex;justify-content:flex-end;margin-top:10px}.complete-bar{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-top:18px;padding:14px;border:1px solid #f0d2aa;border-radius:13px;color:#9b5c17;background:#fff8ee}.complete-bar.ready{color:#167354;border-color:#bfe8d7;background:#eaf9f2}.complete-bar p{margin:0;font-size:12px}.readonly-note{display:flex;align-items:center;gap:8px;padding:11px 13px;border-radius:10px;color:#526787;background:#f2f5f9;font-size:11px}@media(max-width:900px){.metadata-grid{grid-template-columns:1fr 1fr}}@media(max-width:700px){.editor-hero{align-items:flex-start;flex-direction:column}.metadata-grid{grid-template-columns:1fr}.complete-bar{align-items:stretch;flex-direction:column}.complete-bar button{width:100%}.text-meta{align-items:flex-start;flex-direction:column}}
</style>
