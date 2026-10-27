<template>
  <section class="page-state" :class="`page-state--${tone}`" :role="tone === 'error' ? 'alert' : 'status'" aria-live="polite">
    <span class="page-state__icon" aria-hidden="true"><AppIcon :name="icon" /></span>
    <div><strong>{{ title }}</strong><p v-if="message">{{ message }}</p></div>
    <div v-if="actionLabel || secondaryActionLabel" class="page-state__actions">
      <button v-if="actionLabel" type="button" class="outline-button" @click="$emit('action')">{{ actionLabel }}</button>
      <button v-if="secondaryActionLabel" type="button" class="page-state__secondary" @click="$emit('secondary-action')">{{ secondaryActionLabel }}</button>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
const props = withDefaults(defineProps<{ tone?: 'loading' | 'empty' | 'error'; title: string; message?: string; actionLabel?: string; secondaryActionLabel?: string }>(), { tone: 'empty', message: '', actionLabel: '', secondaryActionLabel: '' })
defineEmits<{ action: []; 'secondary-action': [] }>()
const icon = computed(() => props.tone === 'loading' ? 'clock' : props.tone === 'error' ? 'connection' : 'document')
</script>
<style scoped>
.page-state{min-height:180px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:30px;text-align:center;border:1px dashed var(--line);border-radius:var(--radius-md);color:var(--muted);background:#fbfcff}.page-state__icon{display:grid;place-items:center;width:44px;height:44px;border-radius:50%;color:var(--blue);background:var(--blue-soft);font-size:24px}.page-state__icon svg{width:23px;height:23px}.page-state strong{display:block;color:var(--ink)}.page-state p{max-width:440px;margin:6px 0 0;font-size:13px;line-height:1.6}.page-state__actions{display:flex;align-items:center;justify-content:center;gap:10px}.page-state__secondary{min-height:40px;padding:9px 16px;border:0;color:var(--muted);background:transparent}.page-state--error .page-state__icon{color:var(--red);background:var(--red-soft)}.page-state--loading .page-state__icon{animation:pulse-state 1.2s ease-in-out infinite}@keyframes pulse-state{50%{opacity:.45;transform:scale(.92)}}
</style>
