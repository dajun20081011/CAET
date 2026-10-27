<template>
  <section class="provider-settings panel">
    <div class="provider-settings__head">
      <div><h2>AI 服务配置</h2><p>密钥加密保存在服务器，页面不会读取或显示原文。</p></div>
      <button class="provider-refresh" type="button" :disabled="loading" @click="load">刷新</button>
    </div>

    <div v-if="error" class="provider-message provider-message--error">{{ error }}</div>
    <div v-if="data && !data.writable" class="provider-message provider-message--warning">
      服务器尚未设置 AI_SETTINGS_MASTER_KEY。现有环境变量仍可使用，但后台暂不能保存新密钥。
    </div>

    <div v-if="data" class="provider-tabs">
      <button v-for="item in data.providers" :key="item.code" type="button"
              :class="{ active: activeCode === item.code }" @click="select(item)">
        <strong>{{ item.label }}</strong>
        <span :class="item.enabled ? 'ready' : ''">{{ item.enabled ? '已启用' : '未启用' }}</span>
      </button>
    </div>

    <form v-if="current" class="provider-form" @submit.prevent="save">
      <div class="provider-form__summary">
        <label class="provider-switch"><input v-model="form.enabled" type="checkbox"> 启用此服务</label>
        <small>当前来源：{{ current.source === 'database' ? '后台加密配置' : '服务器环境变量' }}</small>
      </div>
      <div v-if="activeCode === 'qwen_tts'" class="provider-endpoint-help">
        <span>千问语音合成需使用 SpeechSynthesizer 接口。</span>
        <button type="button" @click="useQwenEndpoint">填入正确地址</button>
      </div>

      <div class="provider-fields">
        <label v-for="field in visibleFields" :key="field">
          <span>{{ fieldLabel(field) }}</span>
          <textarea v-if="field === 'voices'" v-model.trim="form.config[field]" rows="3" :placeholder="fieldPlaceholder(field)" />
          <select v-else-if="field === 'language' && activeCode === 'suntone'" v-model="form.config[field]">
            <option value="cn">中文 cn</option><option value="en">英文 en</option>
          </select>
          <select v-else-if="field === 'core'" v-model="form.config[field]">
            <option value="word">单词 word</option><option value="sent">句子 sent</option><option value="para">篇章 para</option>
          </select>
          <input v-else v-model.trim="form.config[field]" :placeholder="fieldPlaceholder(field)">
        </label>
        <label><span>API Key</span><input v-model.trim="form.api_key" type="password" autocomplete="new-password" :placeholder="secretPlaceholder('api_key')"></label>
        <label v-if="activeCode !== 'qwen_tts'"><span>API Secret</span><input v-model.trim="form.api_secret" type="password" autocomplete="new-password" :placeholder="secretPlaceholder('api_secret')"></label>
      </div>

      <div class="provider-form__actions">
        <span v-if="saved" class="provider-saved">已保存并对新请求生效</span>
        <button type="submit" :disabled="saving || !data?.writable">{{ saving ? '保存中…' : '保存并生效' }}</button>
      </div>
    </form>
    <div v-else-if="loading" class="provider-loading">正在读取 AI 服务配置…</div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { cabinlingoApi, type AIProviderCode, type AIProviderSetting, type AIProviderSettingsResponse } from '@/api'

const emit = defineEmits<{ changed: [] }>()
const data = ref<AIProviderSettingsResponse | null>(null)
const activeCode = ref<AIProviderCode>('qwen_tts')
const loading = ref(false); const saving = ref(false); const error = ref(''); const saved = ref(false)
const form = reactive({ enabled: false, config: {} as Record<string, string>, api_key: '', api_secret: '' })
const current = computed(() => data.value?.providers.find(item => item.code === activeCode.value) || null)
const visibleFields = computed(() => Object.keys(current.value?.config || {}))

const labels: Record<string, string> = { endpoint: '接口地址', workspace_id: 'Workspace ID（可选）', model: '模型', voices: '音色目录', app_id: 'APP ID', provider: '供应商标识', version: '接口版本', language: '语种', domain: '业务领域', accent: '口音', core: '评测题型', dialect: '方言/口音', ent: '评测引擎', category: '评测类别' }
function fieldLabel(field: string) { return labels[field] || field }
function fieldPlaceholder(field: string) { return field === 'voices' ? 'voice_id|显示名称|zh+en；多项用分号分隔' : `填写${fieldLabel(field)}` }
function secretPlaceholder(name: string) { return current.value?.secret_status[name] ? '已安全保存；留空保持不变' : `尚未配置 ${name === 'api_key' ? 'API Key' : 'API Secret'}` }
function useQwenEndpoint() { form.config.endpoint = 'https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer' }
function select(item: AIProviderSetting) {
  activeCode.value = item.code; Object.assign(form, { enabled: item.enabled, config: { ...item.config }, api_key: '', api_secret: '' }); error.value = ''; saved.value = false
}
async function load() {
  loading.value = true; error.value = ''
  try { data.value = await cabinlingoApi.aiProviderSettings(); select(data.value.providers.find(item => item.code === activeCode.value) || data.value.providers[0]) }
  catch { error.value = 'AI 服务配置读取失败，请检查管理员权限和数据库迁移。' }
  finally { loading.value = false }
}
async function save() {
  if (!data.value?.writable) return
  saving.value = true; error.value = ''; saved.value = false
  try {
    data.value = await cabinlingoApi.saveAiProviderSettings(activeCode.value, { enabled: form.enabled, config: { ...form.config }, api_key: form.api_key || undefined, api_secret: form.api_secret || undefined })
    const item = data.value.providers.find(row => row.code === activeCode.value); if (item) select(item)
    saved.value = true; emit('changed')
  } catch (cause: any) { error.value = cause?.response?.data?.detail || '保存失败，请检查必填项。' }
  finally { saving.value = false }
}
onMounted(load)
</script>

<style scoped>
.provider-settings{grid-column:1/-1}.provider-settings__head,.provider-form__summary,.provider-form__actions{display:flex;align-items:center;justify-content:space-between;gap:16px}.provider-settings__head h2{margin:0 0 5px}.provider-settings__head p,.provider-form__summary small{margin:0;color:#8998b2;font-size:11px}.provider-refresh{padding:8px 13px;border:1px solid #bfd6fb;border-radius:9px;color:#1769ed;background:#fff}.provider-message{margin:14px 0 0;padding:11px 13px;border-radius:10px;font-size:12px}.provider-message--error{color:#a84040;background:#fff0f0}.provider-message--warning{color:#9a621c;background:#fff7e8}.provider-tabs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-top:18px}.provider-tabs button{display:flex;align-items:center;justify-content:space-between;gap:7px;padding:12px;border:1px solid #e0e8f4;border-radius:11px;color:#18365f;background:#f8fafd;text-align:left}.provider-tabs button.active{border-color:#2f7cf6;background:#eef5ff}.provider-tabs strong{font-size:12px}.provider-tabs span{flex:none;color:#8998b2;font-size:10px}.provider-tabs span.ready{color:#14976d}.provider-form{margin-top:14px;padding:16px;border:1px solid #dfe8f5;border-radius:13px;background:#fbfcff}.provider-switch{display:flex;align-items:center;gap:8px;color:#17345e;font-size:13px;font-weight:700}.provider-switch input{width:auto}.provider-endpoint-help{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px;padding:9px 11px;border-radius:9px;color:#506b91;background:#eef5ff;font-size:11px}.provider-endpoint-help button{padding:6px 9px;border:1px solid #a9c9f6;border-radius:7px;color:#1768ed;background:#fff}.provider-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:15px}.provider-fields label{display:grid;gap:6px;color:#5d6f8d;font-size:11px;font-weight:600}.provider-fields input,.provider-fields select,.provider-fields textarea{width:100%;box-sizing:border-box;padding:10px 11px;border:1px solid #d9e3f1;border-radius:9px;color:#102f5d;background:#fff}.provider-fields textarea{resize:vertical}.provider-form__actions{justify-content:flex-end;margin-top:15px}.provider-form__actions button{padding:10px 17px;border:0;border-radius:9px;color:#fff;background:#2676f3}.provider-form__actions button:disabled{opacity:.45}.provider-saved{margin-right:auto;color:#15946b;font-size:11px}.provider-loading{padding:25px;text-align:center;color:#8998b2}@media(max-width:900px){.provider-tabs{grid-template-columns:repeat(2,1fr)}}@media(max-width:600px){.provider-fields,.provider-tabs{grid-template-columns:1fr}.provider-form__summary,.provider-endpoint-help{align-items:flex-start;flex-direction:column}}
</style>
