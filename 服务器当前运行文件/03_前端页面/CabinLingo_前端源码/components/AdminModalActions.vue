<template>
  <footer class="modal-actions">
    <button type="button" class="outline-button" :disabled="saving" @click="$emit('close')">取消</button>
    <button type="submit" class="primary-button primary-button--compact" :disabled="saving">{{ saving ? '保存中…' : submitLabel }}</button>
  </footer>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ saving?: boolean; submitLabel?: string }>(), { saving: false, submitLabel: '保存' })
defineEmits<{ close: [] }>()
</script>

<style scoped>
.modal-actions{display:flex;justify-content:flex-end;gap:10px;padding-top:4px}.modal-actions button{min-width:88px;min-height:44px}.modal-actions button:disabled{opacity:.6}@media(max-width:520px){.modal-actions{position:sticky;bottom:0;margin:0 -18px -22px;padding:14px 18px calc(14px + env(safe-area-inset-bottom));background:#fff;border-top:1px solid var(--line)}.modal-actions button{flex:1}}
</style>
