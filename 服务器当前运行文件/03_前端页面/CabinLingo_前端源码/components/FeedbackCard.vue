<template>
  <article class="feedback-card">
    <header><div><span>教员 {{ teacher }}</span><small>{{ date }}</small></div><span v-if="requiredRetraining" class="ui-status warning">需整改</span></header>
    <h2>{{ summary }}</h2><p>{{ advice || '请继续按照课程标准练习。' }}</p>
    <button v-if="requiredRetraining" type="button" class="primary-button primary-button--compact" @click="$emit('retrain')">进入整改训练</button>
  </article>
</template>
<script setup lang="ts">
defineProps<{ teacher: string; date: string; summary: string; advice?: string; requiredRetraining?: boolean }>()
defineEmits<{ retrain: [] }>()
</script>
<style scoped>
.feedback-card{padding:18px;border:1px solid var(--line);border-radius:var(--radius-md);background:#fff;box-shadow:var(--shadow-card)}.feedback-card header{display:flex;justify-content:space-between;align-items:flex-start}.feedback-card header span,.feedback-card header small{display:block;color:var(--muted);font-size:10px}.feedback-card h2{margin:13px 0 7px;color:var(--ink);font-size:17px}.feedback-card p{margin:0 0 14px;color:var(--ink-secondary);line-height:1.7}.feedback-card .primary-button{width:auto}
</style>
