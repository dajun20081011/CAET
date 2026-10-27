<template>
  <section class="assessment-evidence">
    <section class="evidence-card comparison-card">
      <div class="section-heading">
        <div><h4>标准文本与语音识别对比</h4><p>先对照学员实际识别结果，再结合音频进行判断。</p></div>
        <span>{{ changedAlignment.length }} 处差异</span>
      </div>
      <div class="text-comparison">
        <article><h5>标准文本</h5><p>{{ referenceText || '未保存标准文本' }}</p></article>
        <article><h5>语音识别文本</h5><p>{{ recognizedText || '本次结果未保存语音识别文本' }}</p></article>
      </div>
      <div v-if="changedAlignment.length" class="alignment-list">
        <article v-for="(item, index) in changedAlignment" :key="`${item.type}-${item.reference_index}-${index}`" :class="item.type">
          <b>{{ alignmentLabel(item.type) }}</b><span>标准：{{ item.reference || '—' }}</span><span>识别：{{ item.recognized || '—' }}</span>
          <button v-if="typeof item.start_ms === 'number'" type="button" @click="emit('seek', item.start_ms)">播放 {{ formatTime(item.start_ms) }}</button>
        </article>
      </div>
      <p v-else class="inline-empty">没有已保存的文本差异，或本次识别未返回词级对齐。</p>
    </section>

    <section class="evidence-card issue-card">
      <div class="section-heading">
        <div><h4>AI 各维度问题</h4><p>问题数量来自本次真实 AI 结果；待复核内容不会标记为确定错误。</p></div>
        <span>{{ confirmedCount }} 项已确认</span>
      </div>
      <div class="issue-summary" aria-label="AI 各维度问题汇总">
        <article v-for="item in issueSummary" :key="item.type" :class="{ active: item.count > 0 }"><span>{{ item.label }}</span><b>{{ item.count }}</b><small>{{ item.description }}</small></article>
      </div>

      <div v-if="priorityIssues.length" class="priority-block">
        <div class="subheading"><h5>AI 重点问题</h5><span>{{ priorityIssues.length }} 项需优先复核</span></div>
        <div class="focus-list">
          <article v-for="(issue, index) in priorityIssues" :key="issueKey(issue, index)" :class="issue.issue_status === 'pending_review' ? 'pending' : 'confirmed'">
            <div class="focus-word"><strong>{{ issueWord(issue) }}</strong><span>{{ issueLabel(issue.type) }}</span></div>
            <div class="focus-copy"><p>{{ issue.message || '检测到需要结合录音复核的问题。' }}</p><small>{{ issue.issue_status === 'pending_review' ? '待教员复核，不自动作为确定错误' : 'AI 已确认问题' }}</small></div>
            <button v-if="typeof issue.start_ms === 'number'" type="button" @click="emit('seek', issue.start_ms)">▶ {{ formatTime(issue.start_ms) }}</button>
          </article>
        </div>
      </div>
      <p v-else class="empty-result">当前 AI 结果中没有可展示的问题。</p>
    </section>

    <details class="detail-disclosure">
      <summary><span><strong>AI 测评详情</strong><small>综合结果、AI 评分、逐字逐词证据和完整问题记录</small></span><b>展开</b></summary>
      <div class="detail-content">
        <section class="score-overview">
          <div class="score-total" :class="overallTone(overallScore)"><strong>{{ overallScore ?? '—' }}</strong><span>{{ scoreLabel(overallScore) }}</span><small>AI 综合评分</small></div>
          <div class="score-copy"><div><h5>AI 测评结果</h5><span>{{ formatAiStatus(aiStatus) }}</span></div><p>这里展示 AI 已保存的测评数据，不需要教员再次填写各维度分数。</p>
          <div class="dimension-scores">
            <article v-for="item in dimensionScores" :key="item.label"><span>{{ item.label }}</span><b>{{ item.value ?? '—' }}</b><small>{{ item.value === null ? '未返回' : 'AI 评分' }}</small></article>
          </div>
          </div>
        </section>

        <section>
          <div class="subheading"><div><h5>逐字 / 逐词评分</h5><p>正常词采用正文色且不显示绿色 100；橙色为轻微问题，红色为明显问题。</p></div><span>{{ granularWords.length }} 个字词</span></div>
          <div v-if="granularWords.length" class="word-grid">
            <button v-for="(word, index) in granularWords" :key="`${word.word}-${word.start_ms}-${index}`" type="button"
              :class="[scoreTone(word), { selected: selectedWord === word }]" :aria-pressed="selectedWord === word"
              :title="`${word.word} · ${wordScore(word) ?? '未评分'} 分 · ${formatTime(word.start_ms)}`" @click="selectWord(word, index)">
              <strong>{{ word.word }}</strong><b v-if="wordScore(word) !== null && wordScore(word) !== 100">{{ wordScore(word) }}</b>
            </button>
          </div>
          <p v-else class="inline-empty">本次 Suntone 结果只有句级汇总，没有保存逐字或逐词评分。</p>
        </section>

        <article v-if="selectedWord" class="word-detail">
          <div class="word-detail__title"><div><span>当前字词</span><h4>{{ selectedWord.word }}</h4></div><button type="button" @click="playSelectedWord">▶ 播放此处 {{ formatTime(selectedWord.start_ms) }}</button></div>
          <dl>
            <div><dt>字词得分</dt><dd>{{ wordScore(selectedWord) ?? '—' }}</dd></div>
            <div><dt>发音</dt><dd>{{ selectedWord.pronunciation ?? '—' }}</dd></div>
            <div><dt>声调</dt><dd>{{ selectedWord.tone ?? '—' }}</dd></div>
            <div><dt>重音</dt><dd>{{ prominenceLabel(selectedWord.prominence) }}</dd></div>
            <div v-if="selectedWord.expected_pinyin"><dt>标准读音</dt><dd>{{ selectedWord.expected_pinyin }}<template v-if="selectedWord.expected_tone"> · {{ selectedWord.expected_tone }}</template></dd></div>
            <div v-if="selectedWord.detected_tone"><dt>检测声调</dt><dd>{{ selectedWord.detected_tone }}</dd></div>
            <div v-if="selectedWord.pause"><dt>停顿</dt><dd>{{ selectedWord.pause.duration_ms }} ms</dd></div>
            <div><dt>录音位置</dt><dd>{{ formatTime(selectedWord.start_ms) }}</dd></div>
          </dl>
          <div v-if="selectedWord.phonemes?.length" class="phoneme-list"><button v-for="(phoneme,index) in selectedWord.phonemes" :key="`${phoneme.phoneme || phoneme.phone}-${index}`" type="button" @click="playPhoneme(phoneme.start_ms)"><strong>{{ phoneme.phoneme || phoneme.phone || '音素' }}</strong><span>{{ phoneme.pronunciation ?? '—' }}</span></button></div>
          <div v-if="selectedIssues.length" class="selected-issues"><article v-for="(issue,index) in selectedIssues" :key="issueKey(issue, index)"><b>{{ issueLabel(issue.type) }} · {{ issue.issue_status === 'pending_review' ? '待复核' : '已确认' }}</b><p>{{ issue.message || '请结合录音和标准文本复核。' }}</p></article></div>
        </article>

        <section class="analysis-section">
          <div class="subheading"><h5>测评指标与问题详情</h5><span>数据库已有结果</span></div>
          <div class="analysis-metrics">
            <article><span>语速</span><b>{{ speed ?? '—' }}</b><small>{{ speed === null ? '未返回' : '字/词每分钟' }}</small></article>
            <article><span>评测时长</span><b>{{ durationSeconds === null ? '—' : `${durationSeconds}s` }}</b><small>供应商结果</small></article>
            <article><span>逐词粒度</span><b>{{ wordDetailLevel === 'word' ? '逐词' : wordDetailLevel === 'sentence' ? '句级' : '—' }}</b><small>Suntone 返回层级</small></article>
            <article><span>证据状态</span><b>{{ confirmedCount }} / {{ pendingCount }}</b><small>已确认 / 待复核</small></article>
          </div>
          <div v-if="issues.length" class="all-issues">
            <article v-for="(issue,index) in issues" :key="issueKey(issue,index)"><div><b>{{ issueWord(issue) }} · {{ issueLabel(issue.type) }}</b><span>{{ issue.issue_status === 'pending_review' ? '待复核' : '已确认' }}</span></div><p>{{ issue.message || '请结合录音复核。' }}</p><small v-if="issue.training_advice">建议：{{ issue.training_advice }}</small></article>
          </div>
          <p v-else class="inline-empty">本次结果没有保存问题明细。</p>
        </section>
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface LearnerIssue { type?: string; message?: string; severity?: string; issue_status?: 'confirmed' | 'pending_review' | 'filtered'; word?: string; expected?: string; actual?: string; reference_index?: number; start_ms?: number; end_ms?: number; training_advice?: string; [key: string]: unknown }
interface WordPhoneme { phoneme?: string; phone?: string; start_ms?: number; end_ms?: number; pronunciation?: number }
interface WordDetail { word: string; start_ms: number; end_ms: number; overall?: number; pronunciation?: number; tone?: number; prominence?: number; expected_pinyin?: string; expected_tone?: string; detected_tone?: string; char_type?: number; reference_index?: number; detail_level?: 'word' | 'sentence'; pause?: { duration_ms: number }; phonemes?: WordPhoneme[] }
interface TextAlignmentItem { type: 'matched' | 'omission' | 'insertion' | 'substitution'; reference: string | null; recognized: string | null; start_ms: number | null; reference_index: number | null; recognized_index: number | null }

const props = defineProps<{
  referenceText: string
  recognizedText: string | null
  alignment: any[]
  wordDetails: any[]
  wordDetailLevel: 'word' | 'sentence' | null
  issues: any[]
  speed: number | null
  durationSeconds: number | null
  aiScores: Record<string, number>
  overallScore: number | null
  aiStatus: string
}>()
const emit = defineEmits<{ seek: [milliseconds: number] }>()
const selectedWord = ref<WordDetail | null>(null)
const selectedIndex = ref(-1)

const granularWords = computed(() => (props.wordDetails as WordDetail[]).filter(item => item.word && item.char_type !== 1 && item.detail_level !== 'sentence'))
const changedAlignment = computed(() => (props.alignment as TextAlignmentItem[]).filter(item => item.type !== 'matched'))
const confirmedCount = computed(() => (props.issues as LearnerIssue[]).filter(issue => issue.issue_status === 'confirmed').length)
const pendingCount = computed(() => (props.issues as LearnerIssue[]).filter(issue => issue.issue_status === 'pending_review').length)
const priorityIssues = computed(() => [...props.issues as LearnerIssue[]].sort((left, right) => issuePriority(right) - issuePriority(left)).slice(0, 5))
const selectedIssues = computed(() => selectedWord.value ? (props.issues as LearnerIssue[]).filter(issue => {
  if (typeof issue.reference_index === 'number' && issue.reference_index === selectedIndex.value) return true
  if (typeof issue.start_ms === 'number' && typeof issue.end_ms === 'number') return issue.start_ms <= selectedWord.value!.end_ms && issue.end_ms >= selectedWord.value!.start_ms
  return String(issue.word || issue.expected || '').toLowerCase() === selectedWord.value!.word.toLowerCase()
}) : [])
const issueSummary = computed(() => [
  { type: 'word_omitted', label: '漏读', count: countTypes(['word_omitted']), description: '标准文本中未读出的内容' },
  { type: 'word_inserted', label: '增读', count: countTypes(['word_inserted']), description: '标准文本之外的内容' },
  { type: 'word_repeated', label: '回读', count: countTypes(['word_repeated']), description: '重复朗读的内容' },
  { type: 'word_replaced', label: '替换 / 错读', count: countTypes(['word_replaced']), description: '识别文本与标准文本不同' },
  { type: 'pronunciation', label: '发音问题', count: pronunciationCount(), description: '音素、声调或低分字词' },
  { type: 'pause', label: '停顿问题', count: countTypes(['long_pause', 'leading_silence', 'trailing_silence', 'pause_error']), description: '停顿位置或时长异常' },
  { type: 'rhythm', label: '节奏问题', count: countTypes(['rhythm_error', 'speed_error', 'prosody_error']), description: '语速、韵律或表达异常' },
])
const dimensionScores = computed(() => [
  { label: '发音', value: scoreFrom(['pronunciation']) },
  { label: '流畅度', value: scoreFrom(['fluency']) },
  { label: '完整度', value: scoreFrom(['completeness', 'integrity']) },
  { label: '表达与韵律', value: scoreFrom(['expression', 'rhythm', 'tone']) },
])

watch(() => props.wordDetails, () => { selectedWord.value = null; selectedIndex.value = -1 })
function countTypes(types: string[]) { return (props.issues as LearnerIssue[]).filter(issue => types.includes(issue.type || '')).length }
function scoreFrom(keys: string[]) { for (const key of keys) { const value = props.aiScores[key]; if (typeof value === 'number') return value } return null }
function scoreLabel(value: number | null) { return value === null ? '未返回' : value >= 85 ? '优秀' : value >= 70 ? '达标' : '需改进' }
function overallTone(value: number | null) { return value === null ? 'unknown' : value >= 85 ? 'good' : value >= 70 ? 'medium' : 'low' }
function formatAiStatus(value: string) { const statuses=value.split(',').filter(Boolean); const normalized=statuses.length>1 ? (statuses.every(item=>item==='completed')?'completed':statuses.includes('completed')?'partial':statuses.includes('processing')?'processing':statuses.includes('failed')?'failed':statuses[0]) : statuses[0]; return ({completed:'已完成',pending:'等待分析',pending_adapter:'等待服务',processing:'分析中',failed:'分析失败',partial:'部分完成'} as Record<string,string>)[normalized || ''] || normalized || '暂无状态' }
function wordScore(word: WordDetail) { const scores = [word.pronunciation, word.overall, word.expected_tone ? word.tone : undefined].filter((value): value is number => typeof value === 'number'); return scores.length ? Math.min(...scores) : null }
function pronunciationCount() { const issueWords = countTypes(['chinese_tone_error', 'phoneme_error', 'pronunciation_error']); const lowWords = granularWords.value.filter(word => { const score=wordScore(word); return score !== null && score < 70 }).length; return Math.max(issueWords, lowWords) }
function scoreTone(word: WordDetail) { const score=wordScore(word); return score === null || score >= 85 ? 'normal' : score < 70 ? 'low' : 'medium' }
function selectWord(word: WordDetail, index: number) { selectedWord.value = word; selectedIndex.value = typeof word.reference_index === 'number' ? word.reference_index : index; emit('seek', word.start_ms) }
function playSelectedWord() { if (selectedWord.value) emit('seek', selectedWord.value.start_ms) }
function playPhoneme(milliseconds?: number) { if (selectedWord.value) emit('seek', typeof milliseconds === 'number' ? milliseconds : selectedWord.value.start_ms) }
function formatTime(milliseconds: number) { const seconds=Math.max(milliseconds || 0,0)/1000; return `${Math.floor(seconds/60).toString().padStart(2,'0')}:${(seconds%60).toFixed(1).padStart(4,'0')}` }
function prominenceLabel(value?: number) { return value === 1 ? '重读' : value === 2 ? '弱读' : value === 0 ? '普通' : '—' }
function issuePriority(issue: LearnerIssue) { const status=issue.issue_status === 'confirmed' ? 100 : issue.issue_status === 'pending_review' ? 40 : 0; const severity=issue.severity === 'critical' ? 30 : issue.severity === 'error' ? 25 : issue.severity === 'warning' ? 15 : 5; const location=typeof issue.start_ms === 'number' ? 5 : 0; return status + severity + location }
function issueWord(issue: LearnerIssue) { return String(issue.word || issue.expected || issue.actual || '录音片段') }
function issueKey(issue: LearnerIssue, index: number) { return `${issue.type || 'issue'}-${issue.reference_index ?? issue.start_ms ?? index}-${index}` }
function issueLabel(type?: string) { return ({word_omitted:'漏读',word_inserted:'增读',word_repeated:'回读',word_replaced:'替换 / 错读',chinese_tone_error:'声调错误',phoneme_error:'音素问题',pronunciation_error:'发音问题',long_pause:'长时间停顿',leading_silence:'开头等待过长',trailing_silence:'结尾空白过长',pause_error:'停顿问题',rhythm_error:'节奏问题',speed_error:'语速问题',prosody_error:'韵律问题'} as Record<string,string>)[type || ''] || type || 'AI 提示' }
function alignmentLabel(type: TextAlignmentItem['type']) { return ({omission:'漏读',insertion:'增读',substitution:'替换',matched:'一致'} as Record<string,string>)[type] }
</script>

<style scoped>
.assessment-evidence{display:grid;gap:14px}.evidence-card,.detail-disclosure{min-width:0;border:1px solid #dce7f4;border-radius:16px;background:#f9fbfe}.evidence-card{padding:18px}.section-heading,.subheading,.word-detail__title{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.assessment-evidence h4,.assessment-evidence h5{margin:0;color:#102d57}.section-heading h4{font-size:15px}.section-heading p,.subheading p{margin:5px 0 0;color:#7c8ca7;font-size:10px;line-height:1.55}.section-heading>span,.subheading>span{flex:none;padding:5px 8px;border-radius:999px;color:#1768e5;background:#edf4ff;font-size:9px;white-space:nowrap}
.text-comparison{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}.text-comparison article{min-height:132px;padding:14px;border:1px solid #e0e8f3;border-radius:11px;background:#fff}.text-comparison h5{font-size:11px}.text-comparison p{margin:8px 0 0;color:#354f72;font-size:11px;line-height:1.75;white-space:pre-wrap}.alignment-list{display:grid;gap:6px;margin-top:10px}.alignment-list article{display:grid;grid-template-columns:65px 1fr 1fr auto;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;color:#526681;background:#f4f7fb;font-size:9px}.alignment-list b{color:#cf455b}.alignment-list button,.focus-list button,.word-detail__title button,.phoneme-list button{min-height:36px;padding:7px 9px;border:1px solid #a9c9f6;border-radius:7px;color:#1768e5;background:#fff;cursor:pointer}
.issue-summary{display:grid;grid-template-columns:repeat(4,minmax(95px,1fr));gap:8px;margin-top:14px}.issue-summary article{display:grid;grid-template-columns:1fr auto;gap:4px 7px;min-height:76px;padding:10px;border:1px solid #e0e9f6;border-radius:10px;background:#fff}.issue-summary article.active{border-color:#f0c2c9;background:#fff5f6}.issue-summary span{color:#526681;font-size:10px}.issue-summary b{color:#1768e5;font-size:19px}.issue-summary article.active b{color:#d84e62}.issue-summary small{grid-column:1/-1;color:#8998b2;font-size:8px;line-height:1.4}.priority-block{margin-top:16px;padding-top:15px;border-top:1px solid #e4ebf5}.subheading h5{font-size:12px}.focus-list{display:grid;gap:8px;margin-top:9px}.focus-list article{display:grid;grid-template-columns:minmax(92px,.28fr) minmax(170px,1fr) auto;align-items:center;gap:10px;padding:11px;border-left:3px solid #e06476;border-radius:9px;background:#fff5f6}.focus-list article.pending{border-color:#dfa94e;background:#fff9ef}.focus-word strong,.focus-word span,.focus-copy small{display:block}.focus-word strong{color:#17345e;font-size:11px}.focus-word span{margin-top:3px;color:#cf455b;font-size:9px}.focus-list article.pending .focus-word span{color:#b77815}.focus-copy p{margin:0;color:#405675;font-size:10px;line-height:1.55}.focus-copy small{margin-top:3px;color:#8190a8;font-size:8px}.empty-result,.inline-empty{margin:10px 0 0;padding:11px;border-radius:9px;color:#68809d;background:#f1f6fc;font-size:10px}
.detail-disclosure{background:#fff;overflow:hidden}.detail-disclosure>summary{display:flex;align-items:center;justify-content:space-between;min-height:64px;padding:14px 18px;list-style:none;cursor:pointer}.detail-disclosure>summary::-webkit-details-marker{display:none}.detail-disclosure>summary span,.detail-disclosure>summary small{display:block}.detail-disclosure>summary strong{color:#17365f;font-size:14px}.detail-disclosure>summary small{margin-top:4px;color:#8190a8;font-size:9px}.detail-disclosure>summary b{color:#1768e5;font-size:10px}.detail-disclosure[open]>summary{border-bottom:1px solid #e6edf7}.detail-disclosure[open]>summary b{font-size:0}.detail-disclosure[open]>summary b::after{font-size:10px;content:'收起'}.detail-content{display:grid;gap:18px;padding:16px 18px 18px}.detail-content>section{padding-top:16px;border-top:1px solid #e6edf7}.detail-content>section:first-child{padding-top:0;border-top:0}
.score-overview{display:grid;grid-template-columns:118px minmax(0,1fr);align-items:stretch;gap:14px}.score-total{min-height:118px;display:grid;place-items:center;align-content:center;border:1px solid #bfdfd4;border-radius:13px;color:#16a777;background:#eaf8f4}.score-total.medium{color:#c6811d;border-color:#f1d6a8;background:#fff7e9}.score-total.low{color:#d94e62;border-color:#f0c5cc;background:#fff2f4}.score-total.unknown{color:#7890af;border-color:#d9e2ee;background:#f2f5f9}.score-total strong{font-size:40px;line-height:1}.score-total span{margin-top:6px;font-size:11px;font-weight:800}.score-total small{margin-top:5px;font-size:8px}.score-copy>div{display:flex;align-items:center;justify-content:space-between;gap:10px}.score-copy>div span{padding:4px 8px;border-radius:999px;color:#188862;background:#e9f8f2;font-size:9px}.score-copy>p{margin:7px 0;color:#7085a2;font-size:10px;line-height:1.55}.dimension-scores{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin-top:9px}.dimension-scores article{padding:8px;border-radius:8px;background:#f3f7fc}.dimension-scores span,.dimension-scores small{display:block;color:#8090a8;font-size:8px}.dimension-scores b{display:block;margin:4px 0;color:#1768e5;font-size:15px}
.word-grid{display:flex;flex-wrap:wrap;gap:6px;max-height:300px;overflow:auto;margin-top:9px;padding:2px}.word-grid button{display:inline-flex;align-items:center;gap:5px;min-height:38px;padding:7px 9px;border:1px solid transparent;border-radius:7px;color:#17345e;background:transparent;cursor:pointer}.word-grid button b{color:#6f7f98;font-size:9px}.word-grid button.medium{border-color:#e8c17b;color:#9a6211;background:#fff9ed}.word-grid button.low{border-color:#f0a5af;color:#c83e54;background:#fff2f4}.word-grid button.selected{border-color:#2777ef!important;outline:2px solid #2777ef;outline-offset:1px;background:#eef5ff}.word-detail{padding:13px;border-radius:11px;background:#f4f8ff}.word-detail__title span{color:#8090aa;font-size:10px}.word-detail__title h4{margin-top:3px;font-size:18px}.word-detail dl{display:grid;grid-template-columns:repeat(4,minmax(90px,1fr));gap:7px;margin:12px 0 0}.word-detail dl div{padding:8px;border-radius:8px;background:#fff}.word-detail dt{color:#8997ae;font-size:9px}.word-detail dd{margin:3px 0 0;color:#17345e;font-size:12px;font-weight:700}.phoneme-list{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}.phoneme-list button{display:flex;gap:8px}.selected-issues{display:grid;gap:6px;margin-top:9px}.selected-issues article{padding:9px;border-radius:8px;background:#fff7e9}.selected-issues b{font-size:11px}.selected-issues p{margin:5px 0;color:#526681;font-size:11px;line-height:1.6}.analysis-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-top:9px}.analysis-metrics article{padding:9px;border-radius:8px;background:#f6f9fd}.analysis-metrics span,.analysis-metrics small{display:block;color:#8998b2;font-size:9px}.analysis-metrics b{display:block;margin:5px 0;color:#1768e5;font-size:14px}.all-issues{display:grid;gap:6px;margin-top:9px}.all-issues article{padding:9px;border-radius:8px;background:#f7f9fc}.all-issues article>div{display:flex;justify-content:space-between;gap:9px}.all-issues b{color:#263e61;font-size:11px}.all-issues span,.all-issues small{color:#8a6a30;font-size:9px}.all-issues p{margin:5px 0;color:#526681;font-size:10px;line-height:1.5}
@media(max-width:720px){.evidence-card{padding:14px}.section-heading{align-items:flex-start;flex-direction:column}.text-comparison{grid-template-columns:1fr}.text-comparison article{min-height:0}.alignment-list article{grid-template-columns:60px 1fr}.alignment-list span:nth-of-type(2){grid-column:2}.alignment-list button{grid-column:1/-1;justify-self:start}.issue-summary{grid-template-columns:repeat(2,1fr)}.focus-list article{grid-template-columns:1fr}.focus-list button{justify-self:start}.score-overview{grid-template-columns:1fr}.score-total{min-height:96px}.dimension-scores{grid-template-columns:repeat(2,1fr)}.word-detail dl,.analysis-metrics{grid-template-columns:repeat(2,1fr)}}
.section-heading h4{font-size:17px}.section-heading p,.subheading p{font-size:12px}.section-heading>span,.subheading>span{font-size:11px}.text-comparison h5{font-size:13px}.text-comparison p{font-size:14px}.alignment-list article{font-size:12px}.issue-summary span{font-size:12px}.issue-summary small{font-size:11px}.subheading h5{font-size:14px}.focus-word strong{font-size:13px}.focus-word span{font-size:11px}.focus-copy p{font-size:13px}.focus-copy small{font-size:11px}.empty-result,.inline-empty{font-size:12px}.detail-disclosure>summary strong{font-size:16px}.detail-disclosure>summary small{font-size:11px}.detail-disclosure>summary b{font-size:12px}.score-total span{font-size:13px}.score-total small{font-size:11px}.score-copy>p{font-size:12px}.dimension-scores span,.dimension-scores small{font-size:11px}.dimension-scores b{font-size:17px}.word-grid button{font-size:14px}.word-grid button b{font-size:11px}.word-detail__title span{font-size:12px}.word-detail dt{font-size:11px}.word-detail dd{font-size:14px}.selected-issues b{font-size:13px}.selected-issues p{font-size:13px}.analysis-metrics span,.analysis-metrics small{font-size:11px}.all-issues b{font-size:13px}.all-issues span,.all-issues small{font-size:11px}.all-issues p{font-size:13px}
@media(max-width:640px){.assessment-evidence{gap:10px}.evidence-card{padding:13px 11px;border-radius:12px}.section-heading h4{font-size:17px}.section-heading p{font-size:13px}.text-comparison article{padding:12px 10px}.text-comparison h5{font-size:14px}.text-comparison p{font-size:15px;line-height:1.8}.issue-summary{gap:6px}.issue-summary article{min-height:86px;padding:9px}.issue-summary span{font-size:13px}.issue-summary small{font-size:11px}.focus-list article{padding:11px 9px}.focus-word strong,.focus-copy p{font-size:14px}.focus-word span,.focus-copy small{font-size:12px}.detail-disclosure>summary{padding:13px 11px}.detail-disclosure>summary strong{font-size:16px}.detail-disclosure>summary small{font-size:12px;line-height:1.5}.detail-content{padding:13px 10px}.word-grid{gap:7px}.word-grid button{min-height:44px;padding:9px;font-size:15px}.word-detail dl{grid-template-columns:1fr 1fr}.analysis-metrics{grid-template-columns:1fr 1fr}}
@media(max-width:390px){.issue-summary{grid-template-columns:1fr}.dimension-scores{grid-template-columns:1fr 1fr}.word-detail dl,.analysis-metrics{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto;transition:none!important}}
</style>
