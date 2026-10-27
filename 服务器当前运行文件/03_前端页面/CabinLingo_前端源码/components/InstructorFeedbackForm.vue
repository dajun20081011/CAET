<template>
  <section class="feedback-form" aria-labelledby="teacher-feedback-title">
    <header>
      <div>
        <h2 id="teacher-feedback-title">教员点评</h2>
        <p>支持文字、语音点评，也可以边说边转成文字</p>
      </div>
      <span v-if="voiceUrl" class="saved-badge">已录制</span>
    </header>

    <div class="input-actions" aria-label="点评输入方式">
      <button
        type="button"
        class="input-action voice-comment"
        :class="{ active: voiceRecording }"
        :disabled="saving || uploading || !voiceSupported"
        :aria-pressed="voiceRecording"
        @click="$emit('record')"
      >
        <span class="action-icon"><i class="wave-icon" aria-hidden="true"><b/><b/><b/><b/></i></span>
        <span><strong>{{ voiceRecording ? '停止录音' : '语音点评' }}</strong><small>{{ voiceRecording ? '正在录制点评…' : '直接录制语音' }}</small></span>
      </button>
      <button
        type="button"
        class="input-action speech-text"
        :class="{ active: speechActive }"
        :disabled="saving || voiceRecording || !speechSupported"
        :aria-pressed="speechActive"
        @click="$emit('transcribe')"
      >
        <span class="action-icon"><i class="text-icon" aria-hidden="true">文</i></span>
        <span><strong>{{ speechActive ? '停止转换' : '语音转文字' }}</strong><small>{{ speechActive ? '正在识别内容…' : '说话自动填写' }}</small></span>
      </button>
    </div>

    <div v-if="voiceRecording" class="recording-state" role="status">
      <span class="recording-dot"/><strong>正在录音</strong><time>{{ formatDuration(voiceDuration) }}</time>
      <button type="button" @click="$emit('record')">完成</button>
    </div>
    <div v-else-if="voiceUrl" class="voice-preview">
      <audio :src="voiceUrl" controls preload="metadata" aria-label="教员语音点评预览" />
      <span>{{ formatDuration(voiceDuration) }}</span>
      <button type="button" :disabled="saving || uploading" @click="$emit('remove-voice')">删除</button>
    </div>

    <label class="text-label" for="teacher-feedback-text">文字点评</label>
    <textarea
      id="teacher-feedback-text"
      :value="modelValue"
      aria-label="教员点评内容"
      placeholder="输入语气、情感、节奏、停连、重音等反馈…"
      @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
    />
    <p v-if="message" class="form-message" role="status">{{ message }}</p>

    <footer>
      <button type="button" class="pass" :class="{ active: decision === 'pass' }" @click="$emit('decision', 'pass')">✓ 通过</button>
      <button type="button" class="retrain" :class="{ active: decision === 'retraining' }" @click="$emit('decision', 'retraining')">↻ 需要复训</button>
      <button type="button" class="submit" :disabled="submitDisabled" @click="$emit('submit')">{{ saving ? '提交中…' : uploading ? '语音上传中…' : '提交评价' }}</button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  modelValue: string
  decision: 'pass' | 'retraining'
  saving: boolean
  speechActive: boolean
  speechSupported: boolean
  voiceRecording: boolean
  voiceSupported: boolean
  voiceUrl: string
  voiceDuration: number
  uploading: boolean
  message: string
}>()

defineEmits<{
  'update:modelValue': [value: string]
  transcribe: []
  record: []
  'remove-voice': []
  decision: [value: 'pass' | 'retraining']
  submit: []
}>()

const submitDisabled = computed(() => props.saving || props.uploading || props.voiceRecording || (!props.modelValue.trim() && !props.voiceUrl))

function formatDuration(milliseconds: number) {
  const seconds = Math.max(0, Math.round(milliseconds / 1000))
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}
</script>

<style scoped>
.feedback-form{margin-top:24px;padding:20px;border:1px solid #e4ebf4;border-radius:24px;background:#fff;box-shadow:0 10px 30px #0d1a3308}.feedback-form>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.feedback-form h2,.feedback-form p{margin:0}.feedback-form h2{color:#121a29;font-size:18px}.feedback-form header p{margin-top:5px;color:#748197;font-size:12px;line-height:1.5}.saved-badge{flex:none;padding:5px 9px;border-radius:999px;color:#168b5c;background:#eaf9f1;font-size:11px;font-weight:700}.input-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:16px}.input-action{display:grid;grid-template-columns:42px minmax(0,1fr);align-items:center;gap:10px;min-height:72px;padding:10px 12px;border:1px solid #e2e9f3;border-radius:17px;text-align:left;background:#f8faff}.input-action.active{border-color:#7dabf4;background:#eef5ff;box-shadow:0 0 0 2px #2b71e51c}.input-action:disabled{cursor:not-allowed;opacity:.5}.input-action>span:last-child,.input-action strong,.input-action small{display:block}.input-action strong{color:#1b2c47;font-size:14px}.input-action small{margin-top:3px;color:#7a879a;font-size:11px}.action-icon{display:grid;place-items:center;width:42px;height:42px;border-radius:13px;color:#1460dc;background:#e7f0ff}.voice-comment .action-icon{color:#fff;background:#1c68e8}.wave-icon{display:flex;align-items:center;gap:2px;height:20px}.wave-icon b{display:block;width:2px;border-radius:2px;background:currentColor}.wave-icon b:nth-child(1),.wave-icon b:nth-child(4){height:9px}.wave-icon b:nth-child(2){height:17px}.wave-icon b:nth-child(3){height:13px}.active .wave-icon b{animation:voice-wave .8s ease-in-out infinite alternate}.active .wave-icon b:nth-child(2){animation-delay:.15s}.active .wave-icon b:nth-child(3){animation-delay:.3s}.text-icon{font-style:normal;font-size:16px;font-weight:800}.recording-state,.voice-preview{display:grid;grid-template-columns:auto auto 1fr auto;align-items:center;gap:9px;min-height:58px;margin-top:12px;padding:9px 11px;border-radius:15px;background:#f4f7fb}.recording-state strong{color:#d83e4e;font-size:13px}.recording-state time,.voice-preview>span{color:#738197;font-size:12px}.recording-state button,.voice-preview button{min-width:54px;min-height:36px;border-radius:11px;color:#1763de;background:#e6efff;font-weight:700}.recording-dot{width:10px;height:10px;border-radius:50%;background:#e43d4c;box-shadow:0 0 0 5px #e43d4c1a;animation:recording-pulse 1s ease-in-out infinite}.voice-preview{grid-template-columns:minmax(0,1fr) auto auto}.voice-preview audio{width:100%;height:38px}.text-label{display:block;margin:16px 2px 7px;color:#41516a;font-size:12px;font-weight:700}.feedback-form textarea{width:100%;min-height:112px;padding:14px;border:1px solid transparent;border-radius:16px;color:#18263b;background:#f5f8fc;line-height:1.65;resize:vertical;outline:none}.feedback-form textarea:focus{border-color:#9ebff5;box-shadow:0 0 0 3px #1459d112}.form-message{margin-top:8px!important;color:#65758c;font-size:12px;line-height:1.55}.feedback-form footer{display:grid;grid-template-columns:1fr 1.25fr;gap:8px;margin-top:14px}.feedback-form footer button{min-height:46px;border-radius:15px;font-weight:700}.pass{color:#168b5c;background:#ebfaf2}.retrain{color:#e77b17;background:#fff5e6}.pass.active,.retrain.active{box-shadow:inset 0 0 0 2px currentColor}.submit{grid-column:1/-1;color:#fff;background:#1459d1}.submit:disabled{opacity:.45}
@keyframes voice-wave{to{height:5px}}@keyframes recording-pulse{50%{box-shadow:0 0 0 8px #e43d4c0f}}
@media(min-width:700px){.feedback-form footer{grid-template-columns:88px 112px minmax(118px,1fr)}.submit{grid-column:auto}}
@media(max-width:430px){.feedback-form{padding:16px}.input-action{grid-template-columns:36px 1fr;gap:8px;min-height:68px;padding:9px}.action-icon{width:36px;height:36px}.input-action strong{font-size:13px}.input-action small{font-size:10px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
