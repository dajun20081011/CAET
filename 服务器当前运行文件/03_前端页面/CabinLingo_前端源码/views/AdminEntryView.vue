<template>
  <AdminMobileV2View v-if="mobile" />
  <AdminView v-else />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AdminMobileV2View from '@/views/AdminMobileV2View.vue'
import AdminView from '@/views/AdminView.vue'

const mobile = ref(typeof window !== 'undefined' && window.matchMedia('(max-width: 700px)').matches)
let media: MediaQueryList | null = null

function syncViewport(event?: MediaQueryListEvent) {
  mobile.value = event ? event.matches : Boolean(media?.matches)
}

onMounted(() => {
  media = window.matchMedia('(max-width: 700px)')
  syncViewport()
  media.addEventListener('change', syncViewport)
})

onBeforeUnmount(() => media?.removeEventListener('change', syncViewport))
</script>
