import { ref, onMounted, onUnmounted } from 'vue'

export function useLearningHeartbeat(learnerId: string, assignmentId?: string, courseId?: string, contentId?: string) {
  const effectiveSeconds = ref(0)
  const isActive = ref(false)
  let intervalId: ReturnType<typeof setInterval> | null = null
  let lastActivity = Date.now()
  let heartbeatCount = 0

  const ACTIVITY_TIMEOUT = 120000 // 2 minutes
  const HEARTBEAT_INTERVAL = 20000 // 20 seconds

  function recordActivity() {
    lastActivity = Date.now()
    if (!isActive.value) {
      isActive.value = true
      startHeartbeat()
    }
  }

  function startHeartbeat() {
    if (intervalId) return
    intervalId = setInterval(() => {
      const now = Date.now()
      if (now - lastActivity > ACTIVITY_TIMEOUT) {
        isActive.value = false
        stopHeartbeat()
        return
      }
      effectiveSeconds.value += 20
      heartbeatCount++
      // Send heartbeat event
      if (typeof window !== 'undefined') {
        const event = new CustomEvent('learning-heartbeat', {
          detail: { learnerId, assignmentId, courseId, contentId, seconds: effectiveSeconds.value },
        })
        window.dispatchEvent(event)
      }
    }, HEARTBEAT_INTERVAL)
  }

  function stopHeartbeat() {
    if (intervalId) {
      clearInterval(intervalId)
      intervalId = null
    }
  }

  function handleVisibilityChange() {
    if (document.hidden) {
      isActive.value = false
      stopHeartbeat()
    }
  }

  function handleActivity() {
    recordActivity()
  }

  onMounted(() => {
    recordActivity()
    document.addEventListener('visibilitychange', handleVisibilityChange)
    document.addEventListener('click', handleActivity)
    document.addEventListener('scroll', handleActivity)
    document.addEventListener('keydown', handleActivity)
  })

  onUnmounted(() => {
    stopHeartbeat()
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    document.removeEventListener('click', handleActivity)
    document.removeEventListener('scroll', handleActivity)
    document.removeEventListener('keydown', handleActivity)
  })

  return { effectiveSeconds, isActive, recordActivity }
}
