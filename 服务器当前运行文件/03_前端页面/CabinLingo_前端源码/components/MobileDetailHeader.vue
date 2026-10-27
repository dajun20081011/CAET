<template>
  <header class="mobile-detail-header">
    <button type="button" aria-label="返回" @click="$emit('back')"><img :src="chevronLeft" alt=""></button>
    <h1>{{ title }}</h1>
    <span aria-hidden="true" />
  </header>
</template>

<script setup lang="ts">
import chevronLeft from '@/assets/figma/chevron-left.svg'
defineProps<{ title:string }>()
defineEmits<{ back:[] }>()
</script>

<style scoped>
.mobile-detail-header{display:grid;grid-template-columns:40px minmax(0,1fr) 40px;align-items:center;gap:8px;width:100%;height:56px;padding:0 16px}.mobile-detail-header button{display:grid;place-items:center;width:40px;height:40px;min-height:40px;padding:0;border-radius:50%;background:#fff}.mobile-detail-header img{width:20px;height:20px;max-width:none}.mobile-detail-header h1{margin:0;color:#12141a;font-size:17px;line-height:22px;font-weight:600;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.mobile-detail-header>span{width:40px;height:40px}
</style>
