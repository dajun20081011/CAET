<template>
  <section class="tts-studio panel">
    <div class="tts-studio__heading">
      <div><p class="tts-kicker">QWEN TTS</p><h2>AI语音制作</h2><p>生成广播词示范音频，并加入当前课程篇目。</p></div>
      <span class="tts-status" :class="options?.enabled ? 'ready' : 'disabled'">{{ options?.enabled ? '服务已连接' : '服务待配置' }}</span>
    </div>
    <p v-if="error" class="tts-message error" role="alert">{{ error }}</p>
    <p v-if="notice" class="tts-message" role="status">{{ notice }}</p>

    <div class="tts-form">
      <label>语种
        <select v-model="language"><option v-for="item in options?.languages || fallbackLanguages" :key="item.id" :value="item.id">{{ item.label }}</option></select>
      </label>

      <div class="tts-field tts-voice">
        <span>音色</span>
        <button class="tts-voice-selected" type="button" @click="voicePickerOpen = true">
          <span><strong>{{ selectedVoiceLabel || '请选择音色' }}</strong><small>{{ selectedVoiceMeta || '打开官网音色目录' }}</small></span>
          <b>选择音色</b>
        </button>
        <div class="tts-voice-actions">
          <small>当前语种 {{ availableVoices.length }} 个 · 官网目录共 {{ options?.voice_count || options?.voices.length || 0 }} 个</small>
          <button type="button" :disabled="busy || !voice || !options?.enabled" @click="previewVoice">{{ previewing ? '生成中…' : '试听当前音色' }}</button>
        </div>
      </div>

      <label class="tts-rate">生成语速
        <div class="tts-rate-control">
          <button type="button" aria-label="降低生成语速" @click="adjustGenerationRate(-rateControl.step)">−</button>
          <input v-model.number="generationRate" type="range" :min="rateControl.min" :max="rateControl.max" :step="rateControl.step" aria-label="生成语速">
          <button type="button" aria-label="提高生成语速" @click="adjustGenerationRate(rateControl.step)">＋</button>
          <input v-model.number="generationRate" class="tts-rate-number" type="number" :min="rateControl.min" :max="rateControl.max" :step="rateControl.step" aria-label="生成语速数值" @change="normalizeGenerationRate">
          <span>x</span>
        </div>
        <small :class="{ warning: !generationRateRecommended }">{{ generationRateRecommended ? '广播推荐范围 0.85–1.15x' : '已超出广播推荐范围' }} · <button type="button" @click="resetGenerationRate">恢复 1.00x</button></small>
      </label>

      <label>音频格式
        <select v-model="format"><option value="mp3">MP3</option><option value="wav">WAV</option></select>
      </label>

      <label class="tts-text">合成文本
        <textarea v-model="text" :maxlength="options?.max_text_chars || 5000" rows="7" placeholder="请输入需要生成的广播词……"></textarea>
        <small>{{ text.length }}/{{ options?.max_text_chars || 5000 }}</small>
      </label>
      <section v-if="language === 'zh'" class="tts-pronunciation" aria-labelledby="tts-pronunciation-title">
        <header>
          <div><strong id="tts-pronunciation-title">多音字发音检查</strong><small>航空词典优先，未命中词语按当前句子判断；生成时不修改原文。</small></div>
          <div><button type="button" :disabled="pronunciationLoading || !text.trim()" @click="checkPronunciation(true)">{{ pronunciationLoading ? '检查中…' : '检查发音' }}</button><button type="button" @click="openLexicon">管理词典</button></div>
        </header>
        <div v-if="pronunciationItems.length" class="tts-pronunciation__items">
          <label v-for="item in pronunciationItems" :key="`${item.phrase}-${item.occurrences[0]?.start}`" :class="{ predicted: item.confidence === 'predicted', disabled: !item.applied }">
            <input v-model="item.applied" type="checkbox">
            <span><strong>{{ item.phrase }}</strong><em>{{ item.confidence === 'confirmed' ? '词典确认' : '语境预测' }}</em></span>
            <input v-model.trim="item.pinyin" type="text" :aria-label="`${item.phrase}的数字声调拼音`">
          </label>
        </div>
        <p v-else>{{ pronunciationCheckedText ? '当前文本没有发现需要强制指定的多音词。' : '输入中文广播词后点击检查；直接生成时也会自动检查。' }}</p>
        <p v-if="pronunciationRequiresReview" class="tts-pronunciation__warning">含语境预测项，请试听确认；如需长期固定，可加入发音词典。</p>
      </section>
      <button class="tts-generate" type="button" :disabled="busy || !canGenerate" @click="generate">{{ generating ? '正在生成音频…' : '生成音频' }}</button>
    </div>

    <div v-if="audioUrl" class="tts-result">
      <div class="tts-result__title"><div><strong>生成结果</strong><small>{{ generatedVoiceLabel }} · {{ generatedRate.toFixed(2) }}x · {{ generatedFormat.toUpperCase() }}</small></div></div>
      <div class="tts-player">
        <button class="tts-play" type="button" @click="togglePlayback">{{ playing ? '❚❚ 暂停' : '▶ 播放' }}</button>
        <input type="range" min="0" :max="duration || 0" step="0.1" :value="currentTime" @input="seek">
        <time>{{ timeLabel(currentTime) }} / {{ timeLabel(duration) }}</time>
        <audio ref="audio" :src="audioUrl" @timeupdate="syncAudio" @loadedmetadata="syncAudio" @play="playing = true" @pause="playing = false" @ended="playing = false" />
      </div>
      <div class="tts-speed">
        <span>播放速度（不重新生成）</span>
        <button v-for="item in playbackRates" :key="item" type="button" :class="{ active: playbackRate === item }" @click="setPlaybackRate(item)">{{ item }}x</button>
        <input v-model.number="playbackRate" type="range" min="0.5" max="2" step="0.05" aria-label="播放速度" @input="applyPlaybackRate">
        <strong>{{ playbackRate.toFixed(2) }}x</strong>
      </div>
      <div class="tts-actions">
        <button type="button" @click="download">下载{{ generatedFormat.toUpperCase() }}</button>
        <button type="button" :disabled="busy" @click="regenerateAtPlaybackRate">按当前速度重新生成</button>
        <button type="button" :disabled="attaching || !canAttach" @click="attachToCourse">{{ attaching ? '正在加入…' : '加入课程' }}</button>
        <button type="button" :disabled="attaching || !canSetStandard" @click="setAsStandard">{{ attaching ? '正在保存…' : '设为示范音频' }}</button>
      </div>
      <p class="tts-context">{{ contextHint }}</p>
    </div>

    <Teleport to="body">
      <div v-if="voicePickerOpen" class="voice-catalog-mask" role="presentation" @click.self="voicePickerOpen = false" @keydown.esc="voicePickerOpen = false">
        <section class="voice-catalog" role="dialog" aria-modal="true" aria-labelledby="voice-catalog-title">
          <header>
            <div><p>QWEN-AUDIO-3.0-TTS-FLASH</p><h3 id="voice-catalog-title">官方音色目录</h3><span>系统音色与官方基础音色，字段按官网目录呈现</span></div>
            <button type="button" aria-label="关闭音色目录" @click="voicePickerOpen = false">×</button>
          </header>
          <div class="voice-catalog__filters">
            <label>搜索<input v-model.trim="voiceQuery" type="search" placeholder="名称、音色特点或 voice 参数"></label>
            <label>适用场景<select v-model="voiceScene"><option value="">全部场景</option><option v-for="item in voiceScenes" :key="item" :value="item">{{ item }}</option></select></label>
            <label>性别<select v-model="voiceGender"><option value="">全部</option><option value="female">女声</option><option value="male">男声</option><option value="unknown">未标注</option></select></label>
            <label>音色来源<select v-model="voiceSource"><option value="">全部</option><option value="system">系统音色</option><option value="basic">基础音色</option><option value="custom">自定义音色</option></select></label>
          </div>
          <div class="voice-catalog__summary">
            <span>{{ language === 'zh' ? '中文' : 'English' }}</span>
            <strong>找到 {{ catalogFilteredVoices.length }} 个音色</strong>
            <button v-if="voiceQuery || voiceScene || voiceGender || voiceSource" type="button" @click="resetVoiceFilters">清除筛选</button>
          </div>
          <div v-if="catalogPageVoices.length" class="voice-catalog__grid">
            <article v-for="item in catalogPageVoices" :key="item.id" :class="{ selected: item.id === voice }">
              <div class="voice-card__title"><strong>{{ item.label }}</strong><span>{{ sourceLabel(item.source) }}</span></div>
              <p>{{ item.trait || '音色特点未标注' }}</p>
              <dl><div><dt>性别</dt><dd>{{ genderLabel(item.gender) }}</dd></div><div><dt>年龄</dt><dd>{{ item.age ? `${item.age}岁` : '未标注' }}</dd></div><div><dt>场景</dt><dd>{{ item.category || '其他' }}</dd></div><div><dt>语种</dt><dd>{{ item.languages.includes('zh') ? '中文' : '英文' }}</dd></div></dl>
              <code :title="item.id">{{ item.id }}</code>
              <footer><button type="button" :disabled="busy || !options?.enabled" @click="previewCatalogVoice(item)">{{ previewing && voice === item.id ? '生成中…' : '试听' }}</button><button class="primary" type="button" @click="selectVoice(item)">{{ voice === item.id ? '已选择' : '选择' }}</button></footer>
            </article>
          </div>
          <div v-else class="voice-catalog__empty">没有符合筛选条件的音色。</div>
          <footer class="voice-catalog__pagination">
            <span>第 {{ voicePage }} / {{ voicePageCount }} 页</span>
            <div><button type="button" :disabled="voicePage <= 1" @click="voicePage--">上一页</button><button type="button" :disabled="voicePage >= voicePageCount" @click="voicePage++">下一页</button></div>
          </footer>
        </section>
      </div>
      <div v-if="lexiconOpen" class="voice-catalog-mask" role="presentation" @click.self="lexiconOpen = false" @keydown.esc="lexiconOpen = false">
        <section class="pronunciation-catalog" role="dialog" aria-modal="true" aria-labelledby="pronunciation-catalog-title">
          <header><div><p>AVIATION PRONUNCIATION</p><h3 id="pronunciation-catalog-title">发音纠错词典</h3><span>内置词典来自 2026.09 广播员考试广播词；人工规则优先级更高。</span></div><button type="button" aria-label="关闭发音词典" @click="lexiconOpen = false">×</button></header>
          <div class="pronunciation-catalog__body">
            <aside>
              <div class="pronunciation-catalog__toolbar"><input v-model.trim="lexiconQuery" type="search" placeholder="搜索词语、拼音或说明"><button type="button" @click="newLexiconEntry">＋新增</button></div>
              <div v-if="lexiconLoading" class="pronunciation-catalog__empty">正在读取词典…</div>
              <div v-else-if="filteredLexicon.length" class="pronunciation-catalog__list">
                <button v-for="entry in filteredLexicon" :key="`${entry.source}-${entry.id}`" type="button" :class="{ active: lexiconForm.phrase === entry.phrase }" @click="editLexiconEntry(entry)">
                  <span><strong>{{ entry.phrase }}</strong><small>{{ entry.pinyin }}</small></span><em>{{ entry.source === 'manual' ? '人工' : '内置' }}</em>
                </button>
              </div>
              <div v-else class="pronunciation-catalog__empty">没有符合条件的词语。</div>
            </aside>
            <form @submit.prevent="saveLexiconEntry">
              <h4>{{ lexiconEditing ? '编辑发音规则' : '新增发音规则' }}</h4>
              <label>词语<input v-model.trim="lexiconForm.phrase" :disabled="Boolean(lexiconEditing)" required maxlength="40" placeholder="例如：座椅夹缝"></label>
              <label>数字声调拼音<input v-model.trim="lexiconForm.pinyin" required maxlength="400" placeholder="zuo4 yi3 jia1 feng4"><small>每个汉字对应一个拼音，轻声使用 5。</small></label>
              <label>使用说明<textarea v-model.trim="lexiconForm.note" rows="4" maxlength="1000" placeholder="适用广播或语境"></textarea></label>
              <label class="pronunciation-catalog__enabled"><input v-model="lexiconForm.enabled" type="checkbox">启用此规则</label>
              <div class="pronunciation-catalog__actions"><button v-if="lexiconEditing?.source === 'manual'" class="danger" type="button" :disabled="lexiconSaving" @click="deleteLexiconEntry">删除人工规则</button><button type="submit" :disabled="lexiconSaving || !lexiconForm.phrase || !lexiconForm.pinyin">{{ lexiconSaving ? '保存中…' : lexiconEditing?.source === 'builtin' ? '建立人工覆盖' : '保存规则' }}</button></div>
              <p v-if="lexiconError" class="tts-message error" role="alert">{{ lexiconError }}</p>
              <p class="pronunciation-catalog__hint">内置规则不能直接删除；建立人工覆盖后可修改读音或停用，删除覆盖即可恢复内置规则。</p>
            </form>
          </div>
        </section>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { cabinlingoApi, type ContentItem, type CourseStandard, type TTSOptions, type TTSPronunciationEntry, type TTSPronunciationItem, type TTSVoiceOption } from '@/api'

const props = defineProps<{ content: ContentItem | null; versionStatus: string | null; standard: CourseStandard | null }>()
const emit = defineEmits<{ attached: []; standardUpdated: [value: CourseStandard] }>()
const options = ref<TTSOptions | null>(null)
const language = ref<'zh' | 'en'>('zh')
const voice = ref('')
const voiceQuery = ref('')
const voicePickerOpen = ref(false)
const voiceScene = ref('')
const voiceGender = ref('')
const voiceSource = ref('')
const voicePage = ref(1)
const voicePageSize = 24
const generationRate = ref(1)
const format = ref<'mp3' | 'wav'>('mp3')
const text = ref('')
const audioBlob = ref<Blob | null>(null)
const audioUrl = ref('')
const audio = ref<HTMLAudioElement | null>(null)
const generatedRate = ref(1)
const generatedVoiceLabel = ref('')
const generatedFormat = ref<'mp3' | 'wav'>('mp3')
const generating = ref(false)
const previewing = ref(false)
const attaching = ref(false)
const playing = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const playbackRate = ref(1)
const error = ref('')
const notice = ref('')
const pronunciationItems = ref<TTSPronunciationItem[]>([])
const pronunciationCheckedText = ref('')
const pronunciationLoading = ref(false)
const pronunciationRequiresReview = ref(false)
const lexiconOpen = ref(false)
const lexiconLoading = ref(false)
const lexiconSaving = ref(false)
const lexiconError = ref('')
const lexiconQuery = ref('')
const lexiconEntries = ref<TTSPronunciationEntry[]>([])
const lexiconEditing = ref<TTSPronunciationEntry | null>(null)
const lexiconForm = reactive({ phrase: '', pinyin: '', note: '', enabled: true, priority: 100 })
const fallbackLanguages = [{ id: 'zh' as const, label: '中文' }, { id: 'en' as const, label: 'English' }]
const playbackRates = [0.75, 1, 1.25]

const rateControl = computed(() => options.value?.rate_control || {
  min: 0.5, max: 2, step: 0.05, default: 1, recommended_min: 0.85, recommended_max: 1.15,
})
const availableVoices = computed(() => (options.value?.voices || []).filter(item => item.languages.includes(language.value)))
const voiceScenes = computed(() => [...new Set(availableVoices.value.map(item => item.category).filter((value): value is string => Boolean(value)))].sort((a, b) => a.localeCompare(b, 'zh-CN')))
const catalogFilteredVoices = computed(() => {
  const query = voiceQuery.value.toLocaleLowerCase()
  return availableVoices.value.filter(item => {
    if (voiceScene.value && item.category !== voiceScene.value) return false
    if (voiceGender.value && item.gender !== voiceGender.value) return false
    if (voiceSource.value && item.source !== voiceSource.value) return false
    return !query || [item.label, item.id, item.trait, item.category]
      .some(value => String(value || '').toLocaleLowerCase().includes(query))
  })
})
const voicePageCount = computed(() => Math.max(1, Math.ceil(catalogFilteredVoices.value.length / voicePageSize)))
const catalogPageVoices = computed(() => catalogFilteredVoices.value.slice((voicePage.value - 1) * voicePageSize, voicePage.value * voicePageSize))
const selectedVoice = computed(() => (options.value?.voices || []).find(item => item.id === voice.value))
const selectedVoiceLabel = computed(() => selectedVoice.value?.label || voice.value)
const selectedVoiceMeta = computed(() => {
  const item = selectedVoice.value
  if (!item) return ''
  const gender = item.gender === 'female' ? '女声' : item.gender === 'male' ? '男声' : ''
  return [gender, item.trait, sourceLabel(item.source)].filter(Boolean).join(' · ')
})
const generationRateRecommended = computed(() => generationRate.value >= rateControl.value.recommended_min && generationRate.value <= rateControl.value.recommended_max)
const canGenerate = computed(() => Boolean(options.value?.enabled && text.value.trim() && voice.value))
const canAttach = computed(() => Boolean(audioBlob.value && props.content && props.versionStatus === 'draft' && !props.content.learning_card_id))
const canSetStandard = computed(() => Boolean(canAttach.value && props.standard))
const contextHint = computed(() => {
  if (!props.content) return '请在下方课程标准库选择一个篇目，再加入课程。'
  if (props.versionStatus !== 'draft') return '已发布版本不可修改，请选择课程草稿。'
  if (props.content.learning_card_id) return '学习卡片保持独立资源，不能直接挂载课程音频。'
  if (!props.standard) return `当前篇目：${props.content.title}。配置训练标准后才能设为示范音频。`
  return `当前篇目：${props.content.title}。可加入课程或设为训练标准示范音频。`
})
const busy = computed(() => generating.value || previewing.value || attaching.value || pronunciationLoading.value)
const filteredLexicon = computed(() => { const query=lexiconQuery.value.toLocaleLowerCase(); return lexiconEntries.value.filter(item=>!query||[item.phrase,item.pinyin,item.note].some(value=>String(value||'').toLocaleLowerCase().includes(query))) })

watch(language, () => { resetVoiceFilters(); voice.value = availableVoices.value[0]?.id || '' })
watch(availableVoices, values => { if (!values.some(item => item.id === voice.value)) voice.value = values[0]?.id || '' }, { immediate: true })
watch([voiceQuery, voiceScene, voiceGender, voiceSource], () => { voicePage.value = 1 })
watch([text, language], () => { pronunciationCheckedText.value='';pronunciationItems.value=[];pronunciationRequiresReview.value=false })

function clearAudio(){if(audioUrl.value)URL.revokeObjectURL(audioUrl.value);audioUrl.value='';audioBlob.value=null;currentTime.value=0;duration.value=0;playing.value=false}
async function loadOptions(){try{options.value=await cabinlingoApi.ttsOptions();generationRate.value=rateControl.value.default;voice.value=availableVoices.value[0]?.id||''}catch{error.value='语音合成配置读取失败，请检查服务状态和权限。'}}
async function checkPronunciation(force=false):Promise<TTSPronunciationItem[]|null>{const value=text.value.trim();if(language.value!=='zh'||!value){pronunciationItems.value=[];pronunciationCheckedText.value=value;pronunciationRequiresReview.value=false;return pronunciationItems.value}if(!force&&pronunciationCheckedText.value===value)return pronunciationItems.value;pronunciationLoading.value=true;error.value='';try{const result=await cabinlingoApi.previewTtsPronunciation(value,language.value);pronunciationItems.value=result.items;pronunciationCheckedText.value=value;pronunciationRequiresReview.value=result.requires_review;return result.items}catch(cause:any){error.value=await apiError(cause,'多音字检查失败，已停止生成，请检查数据库迁移。');return null}finally{pronunciationLoading.value=false}}
async function requestAudio(sampleText?:string){error.value='';notice.value='';normalizeGenerationRate();const requestedRate=sampleText?1:generationRate.value;const requestedVoiceLabel=selectedVoiceLabel.value;const requestedFormat=format.value;const requestedText=sampleText||text.value.trim();let pronunciations:undefined|Array<{phrase:string;pinyin:string;applied:boolean}>;if(!sampleText&&language.value==='zh'){const checked=await checkPronunciation();if(checked===null)throw new Error('pronunciation_check_failed');pronunciations=checked.map(item=>({phrase:item.phrase,pinyin:item.pinyin,applied:item.applied}))}const blob=await cabinlingoApi.generateTts({text:requestedText,language:language.value,voice:voice.value,rate:requestedRate,format:requestedFormat,pronunciations});if(sampleText){const url=URL.createObjectURL(blob);const player=new Audio(url);player.onended=()=>URL.revokeObjectURL(url);player.onerror=()=>URL.revokeObjectURL(url);await player.play();return}clearAudio();audioBlob.value=blob;audioUrl.value=URL.createObjectURL(blob);generatedRate.value=requestedRate;generatedVoiceLabel.value=requestedVoiceLabel;generatedFormat.value=requestedFormat;playbackRate.value=1}
async function generate(){if(!canGenerate.value)return;generating.value=true;try{await requestAudio()}catch(cause:any){if(!error.value)error.value=await apiError(cause,'音频生成失败，请检查模型、音色、额度和网络。')}finally{generating.value=false}}
async function previewVoice(){if(!voice.value||!options.value?.enabled)return;previewing.value=true;try{await requestAudio(language.value==='zh'?'欢迎使用 CabinLingo AI 语音制作。':'Welcome to CabinLingo AI voice studio.')}catch(cause:any){error.value=await apiError(cause,'音色试听生成失败。')}finally{previewing.value=false}}
async function previewCatalogVoice(item:TTSVoiceOption){voice.value=item.id;await previewVoice()}
function selectVoice(item:TTSVoiceOption){voice.value=item.id;voicePickerOpen.value=false}
function resetVoiceFilters(){voiceQuery.value='';voiceScene.value='';voiceGender.value='';voiceSource.value='';voicePage.value=1}
function genderLabel(value:TTSVoiceOption['gender']){return value==='female'?'女声':value==='male'?'男声':'未标注'}
function sourceLabel(value:TTSVoiceOption['source']){return value==='basic'?'基础音色':value==='custom'?'自定义音色':'系统音色'}
async function openLexicon(){lexiconOpen.value=true;newLexiconEntry();await loadLexicon()}
async function loadLexicon(){lexiconLoading.value=true;lexiconError.value='';try{lexiconEntries.value=(await cabinlingoApi.ttsPronunciations()).items}catch(cause:any){lexiconError.value=await apiError(cause,'发音词典读取失败。')}finally{lexiconLoading.value=false}}
function newLexiconEntry(){lexiconEditing.value=null;Object.assign(lexiconForm,{phrase:'',pinyin:'',note:'',enabled:true,priority:100});lexiconError.value=''}
function editLexiconEntry(entry:TTSPronunciationEntry){lexiconEditing.value=entry;Object.assign(lexiconForm,{phrase:entry.phrase,pinyin:entry.pinyin,note:entry.note||'',enabled:entry.enabled,priority:entry.priority||100});lexiconError.value=''}
async function saveLexiconEntry(){lexiconSaving.value=true;lexiconError.value='';try{await cabinlingoApi.saveTtsPronunciation({...lexiconForm});await loadLexicon();const saved=lexiconEntries.value.find(item=>item.phrase===lexiconForm.phrase);if(saved)editLexiconEntry(saved);pronunciationCheckedText.value='';notice.value='发音规则已保存，下次生成自动生效。'}catch(cause:any){lexiconError.value=await apiError(cause,'发音规则保存失败。')}finally{lexiconSaving.value=false}}
async function deleteLexiconEntry(){const entry=lexiconEditing.value;if(!entry||entry.source!=='manual')return;lexiconSaving.value=true;lexiconError.value='';try{await cabinlingoApi.deleteTtsPronunciation(entry.id);await loadLexicon();newLexiconEntry();pronunciationCheckedText.value='';notice.value='人工规则已删除；如有内置规则，将自动恢复。'}catch(cause:any){lexiconError.value=await apiError(cause,'发音规则删除失败。')}finally{lexiconSaving.value=false}}
function togglePlayback(){if(!audio.value)return;if(audio.value.paused)void audio.value.play();else audio.value.pause()}
function syncAudio(){if(!audio.value)return;currentTime.value=audio.value.currentTime||0;duration.value=Number.isFinite(audio.value.duration)?audio.value.duration:0}
function seek(event:Event){if(!audio.value)return;audio.value.currentTime=Number((event.target as HTMLInputElement).value);syncAudio()}
function setPlaybackRate(value:number){playbackRate.value=value;applyPlaybackRate()}
function applyPlaybackRate(){playbackRate.value=Math.min(2,Math.max(.5,Math.round(playbackRate.value*20)/20));if(audio.value)audio.value.playbackRate=playbackRate.value}
function normalizeGenerationRate(){const config=rateControl.value;const value=Number.isFinite(generationRate.value)?generationRate.value:config.default;generationRate.value=Math.min(config.max,Math.max(config.min,Math.round(value/config.step)*config.step));generationRate.value=Number(generationRate.value.toFixed(2))}
function adjustGenerationRate(delta:number){generationRate.value+=delta;normalizeGenerationRate()}
function resetGenerationRate(){generationRate.value=rateControl.value.default;normalizeGenerationRate()}
async function regenerateAtPlaybackRate(){generationRate.value=playbackRate.value;normalizeGenerationRate();await generate()}
function filename(){const base=(props.content?.title||'CabinLingo-AI语音').replace(/[\\/:*?"<>|]/g,'-').slice(0,80);return `${base}-${generatedRate.value.toFixed(2)}x.${generatedFormat.value}`}
function download(){if(!audioUrl.value)return;const link=document.createElement('a');link.href=audioUrl.value;link.download=filename();link.click()}
function asFile(){if(!audioBlob.value)throw new Error('missing audio');return new File([audioBlob.value],filename(),{type:generatedFormat.value==='mp3'?'audio/mpeg':'audio/wav'})}
async function attachToCourse(){if(!props.content||!canAttach.value)return;attaching.value=true;error.value='';try{await cabinlingoApi.uploadContentAsset(props.content.id,asFile(),'audio');notice.value='生成音频已加入当前课程篇目。';emit('attached')}catch(cause:any){error.value=await apiError(cause,'加入课程失败，请确认当前版本为草稿。')}finally{attaching.value=false}}
async function setAsStandard(){if(!props.content||!props.standard||!canSetStandard.value)return;attaching.value=true;error.value='';try{const saved=await cabinlingoApi.uploadCourseStandardAudio(props.content.id,props.standard.id,asFile());notice.value='已设为当前篇目的示范音频。';emit('standardUpdated',saved)}catch(cause:any){error.value=await apiError(cause,'示范音频保存失败。')}finally{attaching.value=false}}
async function apiError(cause:any,fallback:string){const data=cause?.response?.data;if(data instanceof Blob){try{const value=JSON.parse(await data.text());return value.detail||fallback}catch{return fallback}}return data?.detail||fallback}
function timeLabel(seconds:number){const value=Math.max(0,Math.floor(seconds||0));return `${String(Math.floor(value/60)).padStart(2,'0')}:${String(value%60).padStart(2,'0')}`}
onMounted(loadOptions)
onBeforeUnmount(clearAudio)
</script>

<style scoped>
.tts-studio{margin-bottom:18px}.tts-studio__heading{display:flex;justify-content:space-between;gap:20px}.tts-kicker{margin:0 0 5px;color:#1769ef;font-size:10px;font-weight:800;letter-spacing:.15em}.tts-studio h2{margin:0;color:#102f63}.tts-studio__heading p:last-child{margin:6px 0 0;color:#7b8da9;font-size:12px}.tts-status{align-self:flex-start;padding:6px 10px;border-radius:99px;font-size:11px}.tts-status.ready{color:#227b60;background:#eaf9f3}.tts-status.disabled{color:#9a6a19;background:#fff5df}.tts-form{display:grid;grid-template-columns:1fr 1.5fr 1.15fr 1fr;gap:14px;margin-top:18px}.tts-form label{display:grid;align-content:start;gap:7px;color:#516784;font-size:12px}.tts-form select,.tts-form textarea,.tts-form input[type=search],.tts-rate-number,.tts-inline button{min-height:42px;border:1px solid #d4dfef;border-radius:10px;background:#fff;color:#16345f}.tts-form select,.tts-form input[type=search]{padding:0 12px}.tts-inline{display:flex;gap:8px}.tts-inline select{min-width:0;flex:1}.tts-inline button{padding:0 12px;color:#1769ef}.tts-voice-control{display:grid;gap:7px}.tts-voice-control>small{color:#8494ad}.tts-rate-control{display:grid;grid-template-columns:34px minmax(70px,1fr) 34px 66px 12px;align-items:center;gap:6px;min-height:42px}.tts-rate-control button{height:34px;border:1px solid #c6d8f2;border-radius:8px;color:#1769ef;background:#fff;font-size:18px}.tts-rate-control input[type=range]{min-width:0;width:100%;accent-color:#1769ef}.tts-rate-number{width:66px;min-height:36px;padding:0 6px;text-align:center}.tts-rate>small{color:#7185a3}.tts-rate>small.warning{color:#c2761e}.tts-rate>small button{padding:0;color:inherit;text-decoration:underline;background:none}.tts-text{position:relative;grid-column:1/-1}.tts-text textarea{resize:vertical;padding:13px;line-height:1.7}.tts-text small{position:absolute;right:10px;bottom:8px;color:#91a0b5}.tts-generate{grid-column:4;min-height:44px;border-radius:10px;color:#fff;background:#1769ef;box-shadow:0 8px 20px #1769ef2e}.tts-form button:disabled,.tts-actions button:disabled{cursor:not-allowed;opacity:.45}.tts-message{margin:14px 0 0;padding:10px 12px;border-radius:9px;color:#237d61;background:#eaf9f3}.tts-message.error{color:#a44450;background:#fff0f2}.tts-result{margin-top:20px;padding:18px;border:1px solid #d8e5f7;border-radius:15px;background:#f8fbff}.tts-result__title strong,.tts-result__title small{display:block}.tts-result__title small{margin-top:4px;color:#7b8da9}.tts-player{display:grid;grid-template-columns:110px minmax(100px,1fr) auto;align-items:center;gap:12px;margin-top:15px}.tts-player audio{display:none}.tts-play{min-height:42px;border-radius:9px;color:#fff;background:#2d7df0}.tts-player input{width:100%;accent-color:#2d7df0}.tts-player time{color:#6d7f9b;font-size:11px}.tts-speed,.tts-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:14px}.tts-speed span{margin-right:5px;color:#516784;font-size:12px}.tts-speed input{width:150px;accent-color:#1769ef}.tts-speed strong{min-width:45px;color:#1769ef;font-size:12px}.tts-speed button,.tts-actions button{min-height:38px;padding:0 12px;border:1px solid #bcd1ef;border-radius:9px;color:#1769ef;background:#fff}.tts-speed button.active{color:#fff;border-color:#1769ef;background:#1769ef}.tts-actions button:nth-last-child(-n+2){color:#fff;border-color:#1769ef;background:#1769ef}.tts-context{margin:12px 0 0;color:#7c8ca5;font-size:11px}@media(max-width:1000px){.tts-form{grid-template-columns:1fr 1fr}.tts-generate{grid-column:2}}@media(max-width:800px){.tts-player{grid-template-columns:100px 1fr}.tts-player time{grid-column:1/-1;text-align:right}}@media(max-width:520px){.tts-form{grid-template-columns:1fr}.tts-generate{grid-column:1}.tts-inline{flex-wrap:wrap}.tts-inline button{width:100%}.tts-player{grid-template-columns:1fr}.tts-player time{text-align:left}.tts-actions button{width:100%}.tts-rate-control{grid-template-columns:34px minmax(70px,1fr) 34px 66px 12px}}
.tts-field{display:grid;align-content:start;gap:7px;color:#516784;font-size:12px}.tts-voice-selected{min-height:52px;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 11px;border:1px solid #bcd1ef;border-radius:10px;background:#fff;text-align:left}.tts-voice-selected span{min-width:0}.tts-voice-selected strong,.tts-voice-selected small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.tts-voice-selected strong{color:#16345f;font-size:13px}.tts-voice-selected small{max-width:260px;margin-top:4px;color:#7d8da6;font-size:10px}.tts-voice-selected b{flex:none;color:#1769ef;font-size:11px}.tts-voice-actions{display:flex;align-items:center;justify-content:space-between;gap:8px}.tts-voice-actions small{color:#8494ad}.tts-voice-actions button{padding:0;color:#1769ef;background:none;font-size:11px}
.tts-pronunciation{grid-column:1/-1;padding:14px;border:1px solid #d7e4f4;border-radius:12px;background:#f8fbff}.tts-pronunciation>header{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.tts-pronunciation>header strong,.tts-pronunciation>header small{display:block}.tts-pronunciation>header strong{color:#17375f}.tts-pronunciation>header small{margin-top:4px;color:#7b8ca6;font-size:10px}.tts-pronunciation>header>div:last-child{display:flex;gap:7px}.tts-pronunciation button{min-height:34px;padding:0 10px;border:1px solid #bcd1ef;border-radius:8px;color:#1769ef;background:#fff}.tts-pronunciation>p{margin:10px 0 0;color:#7c8ca4;font-size:10px}.tts-pronunciation>p.tts-pronunciation__warning{color:#a66616}.tts-pronunciation__items{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.tts-pronunciation__items label{display:grid;grid-template-columns:auto auto minmax(140px,1fr);align-items:center;gap:7px;min-width:260px;padding:7px 9px;border:1px solid #b7dccf;border-radius:9px;background:#f2fbf7}.tts-pronunciation__items label.predicted{border-color:#efcf96;background:#fffaf0}.tts-pronunciation__items label.disabled{opacity:.55}.tts-pronunciation__items label>span strong,.tts-pronunciation__items label>span em{display:block}.tts-pronunciation__items label>span strong{color:#17375f}.tts-pronunciation__items label>span em{margin-top:2px;color:#6b947f;font-size:8px;font-style:normal}.tts-pronunciation__items label.predicted>span em{color:#a66b18}.tts-pronunciation__items label>input[type=text]{min-height:31px;padding:0 8px;border:1px solid #d0dcec;border-radius:7px;color:#365473;background:#fff;font:10px/1.2 ui-monospace,monospace}
.voice-catalog-mask{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:24px;background:#10234499;backdrop-filter:blur(3px)}.voice-catalog{width:min(1180px,96vw);max-height:92vh;display:flex;flex-direction:column;overflow:hidden;border-radius:20px;background:#f6f9fe;box-shadow:0 30px 80px #0a1c3b59}.voice-catalog>header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding:22px 26px;border-bottom:1px solid #dce6f4;background:#fff}.voice-catalog>header p{margin:0 0 5px;color:#1769ef;font-size:9px;font-weight:800;letter-spacing:.12em}.voice-catalog>header h3{margin:0;color:#102f63;font-size:23px}.voice-catalog>header span{display:block;margin-top:5px;color:#7b8da9;font-size:11px}.voice-catalog>header button{width:34px;height:34px;border-radius:50%;color:#7183a0;background:#edf3fb;font-size:22px}.voice-catalog__filters{display:grid;grid-template-columns:1.5fr repeat(3,1fr);gap:10px;padding:16px 26px;background:#fff}.voice-catalog__filters label{display:grid;gap:6px;color:#667b99;font-size:10px}.voice-catalog__filters input,.voice-catalog__filters select{height:40px;padding:0 11px;border:1px solid #cfdbed;border-radius:9px;color:#18365f;background:#fff}.voice-catalog__summary{display:flex;align-items:center;gap:10px;padding:12px 26px;color:#657a98;font-size:11px}.voice-catalog__summary>span{padding:5px 9px;border-radius:99px;color:#1769ef;background:#e8f1ff}.voice-catalog__summary strong{color:#17345f}.voice-catalog__summary button{margin-left:auto;color:#1769ef;background:none}.voice-catalog__grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;padding:0 26px 18px;overflow:auto}.voice-catalog__grid article{min-width:0;padding:14px;border:1px solid #d9e4f3;border-radius:13px;background:#fff}.voice-catalog__grid article.selected{border-color:#2f80f7;box-shadow:0 0 0 2px #2f80f71f}.voice-card__title{display:flex;align-items:center;justify-content:space-between;gap:8px}.voice-card__title strong{overflow:hidden;color:#15345f;text-overflow:ellipsis;white-space:nowrap}.voice-card__title span{flex:none;padding:4px 6px;border-radius:6px;color:#4e75ac;background:#edf4fe;font-size:9px}.voice-catalog__grid article>p{height:18px;margin:8px 0;color:#496483;font-size:11px}.voice-catalog dl{display:grid;grid-template-columns:repeat(2,1fr);gap:5px;margin:0}.voice-catalog dl div{display:flex;gap:5px}.voice-catalog dt{color:#95a2b5;font-size:9px}.voice-catalog dd{min-width:0;margin:0;overflow:hidden;color:#506785;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.voice-catalog code{display:block;margin-top:9px;overflow:hidden;color:#8797af;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.voice-catalog article footer{display:flex;justify-content:flex-end;gap:7px;margin-top:11px}.voice-catalog article footer button,.voice-catalog__pagination button{height:30px;padding:0 11px;border:1px solid #bcd1ef;border-radius:7px;color:#1769ef;background:#fff;font-size:10px}.voice-catalog article footer button.primary{color:#fff;border-color:#1769ef;background:#1769ef}.voice-catalog__empty{margin:20px 26px;padding:45px;border-radius:12px;color:#7c8da7;background:#fff;text-align:center}.voice-catalog__pagination{display:flex;align-items:center;justify-content:space-between;padding:13px 26px;border-top:1px solid #dce6f4;color:#7184a1;background:#fff;font-size:10px}.voice-catalog__pagination div{display:flex;gap:8px}.voice-catalog button:disabled{cursor:not-allowed;opacity:.45}@media(max-width:900px){.voice-catalog__filters{grid-template-columns:1fr 1fr}.voice-catalog__grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.voice-catalog-mask{padding:8px}.voice-catalog{max-height:96vh}.voice-catalog__filters{grid-template-columns:1fr;padding:12px 15px}.voice-catalog__grid{grid-template-columns:1fr;padding:0 15px 14px}.voice-catalog>header,.voice-catalog__summary,.voice-catalog__pagination{padding-left:15px;padding-right:15px}}
.pronunciation-catalog{width:min(1040px,96vw);max-height:90vh;display:flex;flex-direction:column;overflow:hidden;border-radius:20px;background:#f7faff;box-shadow:0 30px 80px #0a1c3b59}.pronunciation-catalog>header{display:flex;align-items:flex-start;justify-content:space-between;padding:21px 24px;border-bottom:1px solid #dce6f4;background:#fff}.pronunciation-catalog>header p{margin:0 0 5px;color:#1769ef;font-size:9px;font-weight:800;letter-spacing:.12em}.pronunciation-catalog>header h3{margin:0;color:#102f63}.pronunciation-catalog>header span{display:block;margin-top:5px;color:#7b8da9;font-size:10px}.pronunciation-catalog>header>button{width:34px;height:34px;border-radius:50%;color:#7183a0;background:#edf3fb;font-size:22px}.pronunciation-catalog__body{display:grid;grid-template-columns:1.2fr 1fr;min-height:0;flex:1;overflow:hidden}.pronunciation-catalog aside{display:flex;flex-direction:column;min-height:0;padding:16px;border-right:1px solid #dce6f4}.pronunciation-catalog__toolbar{display:flex;gap:8px}.pronunciation-catalog__toolbar input{min-width:0;flex:1;height:38px;padding:0 10px;border:1px solid #cfdbed;border-radius:8px}.pronunciation-catalog__toolbar button{padding:0 11px;border-radius:8px;color:#fff;background:#1769ef}.pronunciation-catalog__list{display:grid;gap:6px;margin-top:12px;overflow:auto}.pronunciation-catalog__list>button{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 10px;border:1px solid #d8e4f3;border-radius:9px;background:#fff;text-align:left}.pronunciation-catalog__list>button.active{border-color:#2f80f7;background:#eef5ff}.pronunciation-catalog__list span{min-width:0}.pronunciation-catalog__list strong,.pronunciation-catalog__list small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pronunciation-catalog__list strong{color:#17375f}.pronunciation-catalog__list small{margin-top:3px;color:#7f8fa7;font:9px ui-monospace,monospace}.pronunciation-catalog__list em{flex:none;padding:3px 6px;border-radius:6px;color:#52749f;background:#edf4fc;font-size:8px;font-style:normal}.pronunciation-catalog__empty{margin-top:12px;padding:30px;color:#8292a9;text-align:center}.pronunciation-catalog form{display:grid;align-content:start;gap:12px;padding:20px;background:#fff}.pronunciation-catalog form h4{margin:0;color:#17375f}.pronunciation-catalog form label{display:grid;gap:6px;color:#536987;font-size:11px}.pronunciation-catalog form input[type=text],.pronunciation-catalog form textarea{padding:9px 10px;border:1px solid #cfdbed;border-radius:8px;color:#17375f}.pronunciation-catalog form input:disabled{color:#73849c;background:#f2f5f9}.pronunciation-catalog form small{color:#8998ad;font-size:9px}.pronunciation-catalog__enabled{display:flex!important;align-items:center;grid-template-columns:auto 1fr!important}.pronunciation-catalog__actions{display:flex;justify-content:flex-end;gap:8px}.pronunciation-catalog__actions button{min-height:38px;padding:0 13px;border-radius:8px;color:#fff;background:#1769ef}.pronunciation-catalog__actions button.danger{margin-right:auto;color:#a84652;border:1px solid #efc7cc;background:#fff}.pronunciation-catalog__hint{margin:0;color:#8796aa;font-size:9px;line-height:1.6}@media(max-width:720px){.tts-pronunciation>header{display:grid}.tts-pronunciation>header>div:last-child button{flex:1}.tts-pronunciation__items label{width:100%;min-width:0}.pronunciation-catalog__body{grid-template-columns:1fr;overflow:auto}.pronunciation-catalog aside{min-height:270px;border-right:0;border-bottom:1px solid #dce6f4}}
</style>
