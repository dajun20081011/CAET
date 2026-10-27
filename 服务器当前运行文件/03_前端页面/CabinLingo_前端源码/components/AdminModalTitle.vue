<template>
  <header class="modal-heading">
    <div>
      <h2>{{ title }}</h2>
      <p v-if="text">{{ text }}</p>
    </div>
    <button type="button" class="modal-close" aria-label="关闭对话框" @click="$emit('close')">×</button>
  </header>
</template>

<script setup lang="ts">
defineProps<{ title?: string; text?: string }>()
defineEmits<{ close: [] }>()
</script>

<style scoped>
.modal-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.modal-heading h2{margin:0;color:var(--ink);font-size:20px;line-height:1.35}.modal-heading p{margin:6px 0 0;color:var(--muted);font-size:12px;line-height:1.6}.modal-close{display:grid;place-items:center;flex:none;width:44px;height:44px;border-radius:50%;color:#647696;background:#f1f5fb;font-size:24px;line-height:1}.modal-close:hover{color:var(--blue);background:var(--blue-soft)}
</style>
