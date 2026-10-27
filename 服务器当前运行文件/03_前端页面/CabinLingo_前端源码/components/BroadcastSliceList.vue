<template>
  <section class="slice-section">
    <div class="slice-heading"><div><h3>切片列表</h3><p>{{ slices.length }} 段 · 单片最多 1024 字符</p></div></div>
    <div v-if="slices.length" class="slice-list">
      <article v-for="(slice, index) in slices" :key="slice.id" class="slice-card">
        <header><strong>第 {{ slice.slice_no }} 段</strong><small>{{ slice.start_char }}–{{ slice.end_char }} · {{ slice.text.length }} 字符</small></header>
        <textarea :value="slice.text" rows="4" maxlength="1024" :readonly="frozen" :disabled="saving" @change="changeText(slice, $event)" />
        <footer v-if="!frozen"><button type="button" class="outline-button outline-button--small" :disabled="index === 0 || saving" @click="$emit('move', index, -1)">上移</button><button type="button" class="outline-button outline-button--small" :disabled="index === slices.length - 1 || saving" @click="$emit('move', index, 1)">下移</button><button type="button" class="outline-button outline-button--small danger" :disabled="saving" @click="$emit('remove', slice)">删除</button></footer>
      </article>
    </div>
    <div v-else class="empty-panel">当前版本尚未生成切片</div>
    <form v-if="!frozen" class="slice-add" @submit.prevent="addSlice">
      <label><span>新增切片</span><textarea v-model="newText" rows="3" maxlength="1024" placeholder="输入切片正文；默认追加到末尾" required /></label>
      <button class="outline-button" :disabled="saving || !newText.trim()">新增切片</button>
    </form>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { BroadcastSlice } from '@/api'

defineProps<{ slices: BroadcastSlice[]; frozen: boolean; saving: boolean }>()
const emit = defineEmits<{
  update: [slice: BroadcastSlice, changes: { text?: string }]
  remove: [slice: BroadcastSlice]; move: [index: number, direction: -1 | 1]
  add: [payload: { text: string; verified: boolean }]
}>()
const newText = ref('')
function changeText(slice: BroadcastSlice, event: Event) {
  const text = (event.target as HTMLTextAreaElement).value
  if (text !== slice.text) emit('update', slice, { text })
}
function addSlice() {
  if (!newText.value.trim()) return
  emit('add', { text: newText.value, verified: false })
  newText.value = ''
}
</script>

<style scoped>
.slice-section{margin-top:22px}.slice-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.slice-heading h3{margin:0;color:var(--ink);font-size:16px}.slice-heading p{margin:4px 0 0;color:var(--muted);font-size:11px}.slice-list{display:grid;gap:10px}.slice-card{padding:14px;border:1px solid var(--line);border-radius:14px;background:#fff}.slice-card header{display:flex;align-items:center;gap:12px;margin-bottom:9px}.slice-card header small{flex:1;color:var(--muted)}.slice-card textarea,.slice-add textarea{width:100%;padding:11px;border:1px solid #dce5f1;border-radius:10px;color:var(--ink);background:#fbfdff;line-height:1.7;resize:vertical}.slice-card textarea[readonly]{background:#f4f7fb}.slice-card footer{display:flex;justify-content:flex-end;gap:7px;margin-top:9px}.slice-add{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:end;margin-top:14px;padding:14px;border:1px dashed #b9cce8;border-radius:14px;background:#f7faff}.slice-add>label:first-child{display:grid;gap:6px;color:var(--muted);font-size:11px}@media(max-width:700px){.slice-add{grid-template-columns:1fr}.slice-card header{align-items:flex-start;flex-wrap:wrap}.slice-card header small{width:100%;order:3}}
</style>
