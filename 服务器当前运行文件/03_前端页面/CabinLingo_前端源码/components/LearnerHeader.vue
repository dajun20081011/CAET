<template><header class="learner-brand-header"><RouterLink to="/student/home" aria-label="CabinLingo 首页"><LearnerBrand /></RouterLink><RouterLink class="notification" to="/student/feedback" aria-label="查看教员反馈"><AppIcon name="bell" /></RouterLink></header></template>
<script setup lang="ts">import LearnerBrand from './LearnerBrand.vue'; import AppIcon from './AppIcon.vue';
</script>
