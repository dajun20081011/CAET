<template><div :class="{ 'learner-app': learner }"><router-view /></div></template>
<script setup lang="ts">import { computed } from 'vue'; import { useRoute } from 'vue-router'; const route=useRoute(); const learner=computed(()=>route.path.startsWith('/student/'));
</script>
