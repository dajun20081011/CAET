<template>
  <div class="min-h-screen bg-background">
    <main class="page-container pb-20">
      <router-view />
    </main>
    <nav class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-100 z-50">
      <div class="max-w-[420px] mx-auto flex justify-around items-center h-14">
        <router-link to="/student/tasks" class="flex flex-col items-center gap-0.5 text-text-secondary touch-target flex-1 justify-center"
          :class="{ 'text-primary': $route.path.includes('/tasks') }">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" /></svg>
          <span class="text-[10px]">任务</span>
        </router-link>
        <router-link to="/student/assessments" class="flex flex-col items-center gap-0.5 text-text-secondary touch-target flex-1 justify-center"
          :class="{ 'text-primary': $route.path.includes('/assessments') }">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          <span class="text-[10px]">测评</span>
        </router-link>
        <router-link to="/student/record" class="flex flex-col items-center gap-0.5 text-text-secondary touch-target flex-1 justify-center"
          :class="{ 'text-primary': $route.path.includes('/record') }">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          <span class="text-[10px]">记录</span>
        </router-link>
      </div>
    </nav>
  </div>
</template>
