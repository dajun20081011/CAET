// ============================================================
// CAET 事件类型展示元数据（仅前端展示用的标签/颜色映射）
// 真实数据由 @/lib/api 调用自建后端获取，此处不含任何 Mock 数据。
// ============================================================

export const eventTypeMeta: Record<string, { label: string; color: string }> = {
  answer_submit: { label: '答题提交', color: 'primary' },
  weekly_test_submit: { label: '周测提交', color: 'success' },
  recording_complete: { label: '录音完成', color: 'info' },
  recording_start: { label: '开始录音', color: 'info' },
  audio_standard_play: { label: '标准音播放', color: 'gray' },
  audio_slow_play: { label: '慢速音播放', color: 'gray' },
  speech_transcription: { label: '语音转写', color: 'info' },
  copy: { label: '复制', color: 'gray' },
  eudic_lookup: { label: '查词', color: 'warning' },
  favorite_word: { label: '收藏单词', color: 'success' },
  learning_heartbeat: { label: '学习心跳', color: 'gray' },
}

export function eventLabel(type: string): string {
  return eventTypeMeta[type]?.label || type
}

export function eventColor(type: string): string {
  return eventTypeMeta[type]?.color || 'gray'
}
