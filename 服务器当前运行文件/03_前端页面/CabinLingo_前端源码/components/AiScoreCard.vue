<template>
  <article class="ai-score-card">
    <span>{{ label }}</span><strong>{{ value ?? '--' }}</strong><small v-if="hint">{{ hint }}</small>
  </article>
</template>
<script setup lang="ts">
defineProps<{ label: string; value: number | string | null | undefined; hint?: string }>()
</script>
<style scoped>
.ai-score-card{min-width:96px;padding:13px;border:1px solid var(--line);border-radius:13px;background:linear-gradient(145deg,#fff,#f6f9ff)}.ai-score-card span,.ai-score-card small{display:block;color:var(--muted);font-size:11px}.ai-score-card strong{display:block;margin:6px 0 2px;color:var(--blue);font-size:24px;letter-spacing:-.5px}.ai-score-card small{font-size:9px}
</style>
