<template>
  <section class="prosody-studio" aria-labelledby="prosody-title">
    <div v-if="false">
    <header class="studio-intro">
      <div><h1 id="prosody-title">音频制作</h1><p>Prosody Studio · 逐句生成、逐句确认、最终合成</p></div>
      <div class="service-meta"><span class="service-pill" :class="serviceReady ? 'ready' : 'unavailable'"><i />{{ serviceReady ? '服务正常' : '服务不可用' }}</span><small v-if="savedAt">草稿已保存 {{ savedAt }}</small></div>
    </header>

    <div v-if="bootstrapLoading" class="studio-grid" aria-busy="true"><div class="card skeleton" /><div class="card skeleton large" /></div>
    <div v-else class="studio-grid">
      <form class="card settings-card" @submit.prevent="analyze">
        <header class="card-title"><div><h2>内容与声音设置</h2><p>设置场景、文本与统一音色</p></div><button v-if="text" type="button" class="link-button" @click="clearText">清空</button></header>
        <label class="field-label" for="prosody-scene">播报场景</label>
        <select id="prosody-scene" v-model="scene" :disabled="!serviceReady || analyzing" required><option value="" disabled>请选择场景</option><option v-for="item in scenes" :key="item.id" :value="item.id">{{ item.label }} · {{ item.description }}</option></select>
        <div class="field-row"><label class="field-label" for="prosody-text">播报文本</label><span>{{ text.length }} / {{ maxTextChars }}</span></div>
        <textarea id="prosody-text" ref="textInput" v-model="text" :maxlength="maxTextChars" rows="9" :disabled="!serviceReady || analyzing" placeholder="每句话使用完整标点。分析后可逐句编辑、生成和确认。" aria-describedby="text-help text-error" @blur="validateText" />
        <p id="text-help" class="field-help">支持每行一句，也支持直接使用情绪、语速、重音、停连和句尾语调标记。</p>
        <p v-if="fieldError" id="text-error" class="field-error" role="alert">{{ fieldError }}</p>
        <details class="format-guide"><summary>文本格式与停连符号</summary><code>[提醒][稍慢]请您【立即】系好安全带。 // ↓</code><div><span><b>/</b> 约 200ms</span><span><b>//</b> 约 400ms</span><span><b>///</b> 约 700ms</span><span><b>【】</b> 重音</span><span><b>↑ ↓ →</b> 句尾语调</span></div><small>使用标记时必须一行一句；未使用标记时系统按标点自动拆句。</small></details>
        <label class="field-label" for="prosody-voice">音色</label>
        <div class="voice-row"><select id="prosody-voice" v-model="voice" :disabled="!availableVoices.length" required><option value="" disabled>请选择音色</option><option v-for="item in availableVoices" :key="item.id" :value="item.id">{{ item.label }}{{ voiceMeta(item) }}</option></select><button type="button" class="outline-button compact" :disabled="!voice || previewingVoice" @click="previewSelectedVoice">{{ previewingVoice ? '生成中…' : '试听当前音色' }}</button></div>
        <div v-if="voicePreviewUrl" class="mini-player"><span><strong>{{ selectedVoiceLabel }}</strong><small>{{ voicePreviewHint }}</small></span><audio ref="voicePreviewPlayer" :src="voicePreviewUrl" controls preload="auto" /></div>
        <p v-if="voicePreviewError" class="field-error" role="alert">{{ voicePreviewError }}</p>
        <div class="split-fields">
          <label><span class="field-label">语言 / 口音</span><select v-model="language"><option v-for="item in options?.languages || []" :key="item.id" :value="item.id">{{ item.label }}</option></select></label>
          <label><span class="field-label">发音词典</span><button type="button" class="dictionary-button" @click="openDictionary"><span>{{ dictionaryCount ? `${dictionaryCount} 条规则` : '管理规则' }}</span><b>管理 →</b></button></label>
        </div>
        <div class="field-row rate-row"><span class="field-label">基础语速</span><strong>{{ rate.toFixed(2) }}×</strong></div>
        <input v-model.number="rate" type="range" :min="rateControl.min" :max="rateControl.max" :step="rateControl.step" aria-label="基础语速">
        <div class="range-labels"><span>{{ rateControl.min }}×</span><span>建议 {{ rateControl.recommended_min }}–{{ rateControl.recommended_max }}×</span><span>{{ rateControl.max }}×</span></div>
        <div v-if="serviceError" class="inline-alert error" role="alert"><strong>语音服务暂不可用</strong><span>{{ serviceError }}</span><button type="button" @click="loadInitial">重试</button></div>
        <button type="submit" class="primary-button analyze-button" :disabled="!canAnalyze || analyzing">{{ analyzing ? '正在分析语调…' : sentences.length ? '重新分析语调' : '分析语调' }}</button>
      </form>

      <section ref="resultsPanel" class="card workspace-card" tabindex="-1" aria-labelledby="workspace-title">
        <header class="workspace-heading">
          <div><h2 id="workspace-title">逐句音频制作 <span v-if="sentences.length">{{ sentences.length }}</span></h2><p>{{ workspaceSubtitle }}</p></div>
          <dl v-if="sentences.length"><div><dt>已生成</dt><dd>{{ generatedCount }} / {{ sentences.length }}</dd></div><div><dt>已确认</dt><dd>{{ acceptedCount }} / {{ sentences.length }}</dd></div></dl>
        </header>
        <div v-if="analysisExpired" class="expired-banner"><strong>结果已过期</strong><span>整篇文本或场景已变更，请重新分析。</span></div>
        <div v-if="operationError && !sentences.length" class="empty-state error-state" role="alert"><b>!</b><h3>{{ operationError?.title }}</h3><p>{{ operationError?.message }}</p><button class="outline-button" type="button" @click="analyze">重试分析</button></div>
        <div v-else-if="!sentences.length" class="empty-state"><div class="wave-mark" aria-hidden="true"><i v-for="n in 26" :key="n" :style="{ height: `${7 + (n * 11) % 34}px` }" /></div><h3>尚未输入并分析播报文本</h3><p>左侧输入整篇文本后点击“分析语调”，系统会拆分为一句一行。</p></div>
        <template v-else>
          <div class="batch-toolbar">
            <div v-if="batchRunning"><span class="spinner small" />正在生成 {{ batchFinished }} / {{ batchTotal }}</div>
            <div v-else-if="batchTotal"><span class="batch-ok">成功 {{ batchSuccess }}</span><span v-if="batchFailed" class="batch-fail">失败 {{ batchFailed }}</span></div>
            <div v-else>可逐句生成，也可按两路并发批量生成</div>
            <span><button type="button" class="outline-button" :disabled="batchRunning || analysisExpired" @click="generateBatch(false)">生成全部句子</button><button type="button" class="primary-button" :disabled="batchRunning || analysisExpired || !missingCount" @click="generateBatch(true)">仅生成未完成句子</button></span>
          </div>
          <ol class="sentence-list">
            <li v-for="row in sentences" :key="row.id" class="sentence-card" :class="[`state-${row.status}`, { accepted: row.accepted }]">
              <div class="sentence-top"><span class="sentence-index">{{ String(row.index + 1).padStart(2, '0') }}</span><span class="status-pill">{{ statusLabel(row) }}</span><span v-if="row.version" class="version">版本 {{ row.version }}</span></div>
              <textarea v-if="row.editing" v-model="row.draftText" class="sentence-editor" rows="3" maxlength="1000" aria-label="编辑本句文本" />
              <p v-else class="sentence-text">{{ row.text }}</p>
              <div v-if="row.editing" class="sentence-controls">
                <label>语气<select v-model="row.tone"><option v-for="item in toneOptions" :key="item" :value="item">{{ item }}</option></select></label>
                <label>语速<select v-model="row.pace"><option v-for="item in paceOptions" :key="item" :value="item">{{ item }}</option></select></label>
                <label>句尾<select v-model="row.intonation"><option value="fall">下降</option><option value="rise">上扬</option><option value="level">平稳</option></select></label>
                <label>停连<select :value="pausePreset(row.pauseAfterMs)" @change="applyPausePreset(row, $event)"><option value="0">无停顿</option><option value="200">/ 短停</option><option value="400">// 句间</option><option value="700">/// 段落</option><option value="custom">自定义</option></select></label>
                <label v-if="pausePreset(row.pauseAfterMs) === 'custom'">停顿毫秒<input v-model.number="row.pauseAfterMs" type="number" min="0" max="3000" step="20"></label>
                <label class="wide-control">重音词<input v-model="row.emphasisDraft" type="text" maxlength="240" placeholder="多个重音使用、分隔，例如：立即、安全带"><small>重音词必须出现在本句正文中</small></label>
              </div>
              <div v-else class="chips"><span>{{ row.tone }}</span><span>{{ row.pace }}</span><span>{{ pitchLabel(row.pitch) }}</span><span>能量 {{ Math.round(row.energy * 100) }}%</span><span>停连 {{ pauseMarker(row.pauseAfterMs) }} · {{ row.pauseAfterMs }}ms</span><span v-for="word in row.emphasis" :key="word" class="emphasis">重音 {{ word }}</span></div>
              <div v-if="row.audioUrl" class="sentence-player"><audio :src="row.audioUrl" controls preload="metadata" /><small>WAV · {{ selectedVoiceLabel }}</small></div>
              <div v-if="row.error" class="row-error" role="alert">{{ row.error }}</div>
              <div class="sentence-actions">
                <template v-if="row.editing"><button type="button" class="outline-button" @click="cancelEdit(row)">取消</button><button type="button" class="primary-button" :disabled="!row.draftText.trim()" @click="saveEdit(row)">保存修改</button></template>
                <template v-else><button type="button" class="text-action" :disabled="row.status === 'generating'" @click="beginEdit(row)">编辑文本</button><button type="button" class="outline-button" :disabled="row.status === 'generating' || analysisExpired" @click="generateSentence(row)">{{ row.status === 'generating' ? '生成中…' : row.audioBlob ? '重新生成' : row.status === 'error' ? '重试此句' : '生成此句' }}</button><button v-if="row.audioBlob" type="button" :class="row.accepted ? 'outline-button' : 'primary-button'" :disabled="row.status === 'generating' || row.status === 'stale'" @click="toggleAccepted(row)">{{ row.accepted ? '取消确认' : '确认此句' }}</button></template>
              </div>
            </li>
          </ol>
          <section v-if="finalAudioUrl" class="final-result"><div><strong>完整音频已合成</strong><small>{{ sentences.length }} 句 · {{ selectedVoiceLabel }} · {{ languageLabel }} · WAV</small><small v-if="downloadMessage" class="download-message" role="status">{{ downloadMessage }}</small><small v-if="downloadError" class="download-message error" role="alert">{{ downloadError }}</small></div><audio :src="finalAudioUrl" controls preload="metadata" @loadedmetadata="readFinalDuration" /><span><small v-if="finalDuration">总时长 {{ finalDuration }}</small><button type="button" class="outline-button" @click="downloadFinal">下载 WAV</button><button type="button" class="text-action" @click="assembleFinal">重新合成</button></span></section>
        </template>
        <footer v-if="sentences.length" class="final-bar"><div><strong>已确认 {{ acceptedCount }} / {{ sentences.length }}</strong><span>{{ allAccepted ? '所有句子已确认，可以合成完整音频' : `还有 ${sentences.length - acceptedCount} 句未确认` }}</span></div><button type="button" class="primary-button assemble-button" :disabled="!allAccepted || assembling || batchRunning || analysisExpired" @click="assembleFinal">{{ assembling ? '正在合成…' : '合成完整音频' }}</button></footer>
      </section>
    </div>

    </div>

    <header class="studio-intro studio-intro-v3">
      <div><h1 id="prosody-title">音频制作</h1><p>逐句生成 · 满意即锁定 · 只处理未完成句子</p></div>
      <div class="studio-actions">
        <button type="button" class="history-button" disabled title="当前后端尚未提供版本记录能力">↺ 版本记录 · 待接入</button>
        <span class="autosave-pill" :class="{ unavailable: !serviceReady || storageError }" :title="storageError || '制作记录仅保存在当前账号的本机浏览器中'">{{ !serviceReady ? '服务不可用' : storageError ? '本机保存失败' : projectSaving || projectDirty ? '正在保存制作记录…' : projectSavedAt ? '✓ 制作记录已保存' : savedAt ? '✓ 原稿已保存' : '✓ 服务已就绪' }}</span>
      </div>
    </header>

    <p v-if="recoveryMessage" class="recovery-banner" role="status">{{ recoveryMessage }}</p>
    <p v-if="storageError" class="recovery-banner error" role="alert">{{ storageError }}</p>

    <nav class="workflow-stepper" aria-label="音频制作进度">
      <span class="done">1&nbsp;&nbsp;原稿</span>
      <span :class="{ done: sentences.length }">2&nbsp;&nbsp;声音设置</span>
      <span :class="{ active: sentences.length && !allAccepted, done: allAccepted }">3&nbsp;&nbsp;逐句制作</span>
      <span :class="{ active: allAccepted && !finalAudioUrl, done: Boolean(finalAudioUrl) }">4&nbsp;&nbsp;完整合成</span>
    </nav>

    <div v-if="bootstrapLoading" class="studio-grid studio-grid-v3" aria-busy="true"><div class="card skeleton" /><div class="card skeleton large" /></div>
    <div v-else class="studio-grid studio-grid-v3">
      <form class="card settings-card settings-card-v3" @submit.prevent="analyze">
        <header class="card-title"><h2>原稿与全局设置</h2></header>
        <label class="field-label" for="prosody-scene-v3">播报场景</label>
        <select v-if="!sentences.length" id="prosody-scene-v3" v-model="scene" :disabled="!serviceReady || analyzing" required><option value="" disabled>请选择场景</option><option v-for="item in scenes" :key="item.id" :value="item.id">{{ item.label }} · {{ item.description }}</option></select>
        <span v-else class="scene-pill">{{ selectedSceneLabel }}</span>
        <div class="field-row"><label class="field-label" for="prosody-text-v3">原稿{{ sentences.length ? '（只读）' : '' }}</label><span v-if="!sentences.length">{{ text.length }} / {{ maxTextChars }}</span></div>
        <textarea v-if="!sentences.length" id="prosody-text-v3" ref="textInput" v-model="text" :maxlength="maxTextChars" rows="7" :disabled="!serviceReady || analyzing" placeholder="每句话使用完整标点。分析后可逐句编辑、生成和确认。" @blur="validateText" />
        <div v-else id="prosody-text-v3" class="readonly-source">{{ analysisSource.text }}</div>
        <p v-if="sentences.length" class="field-help">已拆分为 {{ sentences.length }} 句 · 后续修改请在右侧逐句完成</p>
        <template v-else>
          <p class="field-help">支持每行一句；也可使用情绪、语速、重音、停连和句尾语调标记。</p>
          <p v-if="fieldError" class="field-error" role="alert">{{ fieldError }}</p>
          <details class="format-guide"><summary>文本格式与停连符号</summary><code>[提醒][稍慢]请您【立即】系好安全带。 // ↓</code><div><span><b>/</b> 约 200ms</span><span><b>//</b> 约 400ms</span><span><b>///</b> 约 700ms</span><span><b>【】</b> 重音</span></div></details>
        </template>

        <div class="section-divider" />
        <h3 class="settings-heading">声音设置</h3>
        <button type="button" class="voice-select-button" :disabled="!availableVoices.length" :aria-expanded="voiceSelectorOpen" @click="voiceSelectorOpen = !voiceSelectorOpen">
          <span><strong>{{ selectedVoiceLabel || '请选择音色' }} <em v-if="isFavorite(voice)">★</em></strong><small>{{ selectedVoiceDescription }}</small></span><b>更换音色 ›</b>
        </button>
        <p class="voice-library-note">音色库支持：我的收藏 / 女声 / 男声 / 场景</p>
        <section v-if="voiceSelectorOpen" class="voice-selector" aria-label="选择音色">
          <header><strong>选择音色</strong><button type="button" @click="voiceSelectorOpen = false">关闭</button></header>
          <input v-model.trim="voiceQuery" type="search" placeholder="⌕  搜索音色名称或场景">
          <nav class="voice-tabs" aria-label="音色分类"><button v-for="item in voiceCategories" :key="item.id" type="button" :class="{ active: voiceCategory === item.id }" @click="voiceCategory = item.id">{{ item.label }}</button></nav>
          <template v-if="voiceCategory === 'scene'"><small class="selector-label">场景筛选</small><nav class="voice-tabs scene-tabs"><button v-for="item in voiceScenes" :key="item.id" type="button" :class="{ active: voiceScene === item.id }" @click="voiceScene = item.id">{{ item.label }}</button></nav></template>
          <div class="voice-options">
            <article v-for="item in filteredVoices" :key="item.id" :class="{ selected: item.id === voice }">
              <button type="button" class="voice-option-main" @click="selectVoice(item)"><strong>{{ item.label }}</strong><small>{{ voiceDescription(item) }}</small></button>
              <button type="button" class="voice-preview" :disabled="previewingVoice" @click="previewVoiceOption(item)">{{ previewingVoiceId === item.id ? '生成中…' : '▶ 试听' }}</button>
              <button type="button" class="favorite-button" :aria-label="isFavorite(item.id) ? '取消收藏' : '收藏音色'" :title="isFavorite(item.id) ? '取消本机收藏' : '收藏到本机'" @click="toggleFavorite(item.id)">{{ isFavorite(item.id) ? '★' : '☆' }}</button>
              <span v-if="item.id === voice" class="voice-check">✓</span>
            </article>
            <p v-if="!filteredVoices.length" class="voice-empty">没有符合当前筛选条件的音色</p>
          </div>
          <small class="voice-local-note">★ 收藏仅保存在当前浏览器，不会写入服务器。</small>
        </section>
        <div v-if="voicePreviewUrl" class="mini-player"><span><strong>音色试听</strong><small>{{ voicePreviewHint }}</small></span><audio ref="voicePreviewPlayer" :src="voicePreviewUrl" controls preload="auto" /></div>
        <p v-if="voicePreviewError" class="field-error" role="alert">{{ voicePreviewError }}</p>
        <div class="quick-settings">
          <label><span class="sr-only">语言 / 口音</span><select v-model="language"><option v-for="item in options?.languages || []" :key="item.id" :value="item.id">{{ item.label }} / {{ item.id === 'zh' ? '普通话' : '默认口音' }}</option></select></label>
          <label><span class="sr-only">基础语速</span><select v-model.number="rate"><option v-for="item in rateChoices" :key="item" :value="item">语速 {{ item.toFixed(2) }}</option></select></label>
        </div>
        <div class="quick-settings secondary">
          <button type="button" class="dictionary-status" @click="openDictionary">词典 {{ options?.pronunciation?.enabled ? '已启用' : '不可用' }}</button>
          <details class="advanced-settings"><summary>高级设置 ▾</summary><div class="field-row rate-row"><span>基础语速</span><strong>{{ rate.toFixed(2) }}×</strong></div><input v-model.number="rate" type="range" :min="rateControl.min" :max="rateControl.max" :step="rateControl.step" aria-label="基础语速"><button type="button" class="dictionary-button" @click="openDictionary"><span>{{ dictionaryCount }} 条发音规则</span><b>管理 →</b></button></details>
        </div>
        <div class="safety-tip"><strong>已确认音频不会被批量覆盖</strong><span>调整全局参数，仅影响后续新生成版本。</span></div>
        <div class="production-standard"><strong>成品标准</strong><b>标准广播音频 · WAV 输出</b><span>完整合成后提供试听与下载；响度、峰值等自动质检待后端接入。</span><small>○ 待完整合成后人工复核</small></div>
        <div v-if="serviceError" class="inline-alert error" role="alert"><strong>语音服务暂不可用</strong><span>{{ serviceError }}</span><button type="button" @click="loadInitial">重试</button></div>
        <button v-if="!sentences.length" type="submit" class="primary-button analyze-button" :disabled="!canAnalyze || analyzing">{{ analyzing ? '正在分析并拆分…' : '分析原稿并开始逐句制作' }}</button>
        <button v-else type="button" class="outline-button restructure-button" @click="restartSource">重新导入 / 重新拆分原稿</button>
        <p v-if="sentences.length" class="structure-note">结构级操作：会重新建立句子拆分关系</p>
      </form>

      <section ref="resultsPanel" class="card workspace-card workspace-card-v3" tabindex="-1" aria-labelledby="workspace-title-v3">
        <header class="workspace-heading"><div><h2 id="workspace-title-v3">逐句制作</h2><p>{{ sentences.length ? '先处理需要你判断的句子；已确认句自动锁定。' : '原稿拆分完成后，可在这里逐句制作与审核。' }}</p></div></header>
        <template v-if="sentences.length">
          <div class="status-summary"><span>{{ sentences.length }} 句</span><span class="confirmed">{{ acceptedCount }} 已确认</span><span>{{ pendingCount }} 待确认</span><span v-if="failedCount" class="failed">{{ failedCount }} 失败</span></div>
          <div class="workspace-tools">
            <nav class="sentence-filters" aria-label="句子筛选"><button v-for="item in sentenceFilters" :key="item.id" type="button" :class="{ active: sentenceFilter === item.id }" @click="sentenceFilter = item.id">{{ item.label }} · {{ item.count }}</button></nav>
            <div class="batch-actions"><span v-if="batchRunning"><i class="spinner small" /> {{ batchFinished }}/{{ batchTotal }}</span><span v-else-if="batchTotal" class="batch-result">成功 {{ batchSuccess }}<b v-if="batchFailed"> · 失败 {{ batchFailed }}</b></span><button type="button" class="outline-button" :disabled="batchRunning || analysisExpired" @click="generateBatch(false)">重新生成全部</button><button type="button" class="primary-button" :disabled="batchRunning || analysisExpired || !missingCount" @click="generateBatch(true)">生成未完成 {{ missingCount }} 句</button></div>
          </div>
        </template>
        <div v-if="analysisExpired" class="expired-banner"><strong>结果已过期</strong><span>整篇文本或场景已变更，请重新拆分原稿。</span></div>
        <div v-if="operationError && !sentences.length" class="empty-state error-state" role="alert"><b>!</b><h3>{{ operationError?.title }}</h3><p>{{ operationError?.message }}</p><button class="outline-button" type="button" @click="analyze">重试分析</button></div>
        <div v-else-if="!sentences.length" class="empty-state"><div class="wave-mark" aria-hidden="true"><i v-for="n in 26" :key="n" :style="{ height: (7 + (n * 11) % 34) + 'px' }" /></div><h3>等待原稿拆分</h3><p>在左侧输入原稿并选择场景，系统会按真实 Prosody 分析结果建立逐句制作清单。</p></div>
        <template v-else>
          <ol class="sentence-list">
            <li v-for="row in filteredSentences" :key="row.id" class="sentence-card" :class="['state-' + row.status, { accepted: row.accepted }]">
              <div class="sentence-top"><span class="sentence-index">{{ String(row.index + 1).padStart(2, '0') }}</span><span class="status-pill">{{ statusLabel(row) }}<template v-if="row.accepted"> · 已锁定</template></span><span v-if="row.version" class="version">版本 {{ row.version }}</span><button v-if="!row.accepted && !row.editing" type="button" class="sentence-settings" :disabled="row.status === 'generating'" @click="beginEdit(row)">本句参数 ▾</button></div>
              <textarea v-if="row.editing" v-model="row.draftText" class="sentence-editor" rows="3" maxlength="1000" aria-label="编辑本句文本" />
              <p v-else class="sentence-text">{{ row.text }}</p>
              <div v-if="row.editing" class="sentence-controls">
                <label>语气<select v-model="row.tone"><option v-for="item in toneOptions" :key="item" :value="item">{{ item }}</option></select></label><label>语速<select v-model="row.pace"><option v-for="item in paceOptions" :key="item" :value="item">{{ item }}</option></select></label><label>句尾<select v-model="row.intonation"><option value="fall">下降</option><option value="rise">上扬</option><option value="level">平稳</option></select></label><label>停连<select :value="pausePreset(row.pauseAfterMs)" @change="applyPausePreset(row, $event)"><option value="0">无停顿</option><option value="200">/ 短停</option><option value="400">// 句间</option><option value="700">/// 段落</option><option value="custom">自定义</option></select></label><label v-if="pausePreset(row.pauseAfterMs) === 'custom'">停顿毫秒<input v-model.number="row.pauseAfterMs" type="number" min="0" max="3000" step="20"></label><label class="wide-control">重音词<input v-model="row.emphasisDraft" type="text" maxlength="240" placeholder="多个重音使用、分隔"><small>重音词必须出现在本句正文中</small></label>
              </div>
              <div v-if="row.audioUrl && !row.editing" class="sentence-player"><audio :src="row.audioUrl" controls preload="metadata" /><small>WAV · {{ selectedVoiceLabel }}</small></div>
              <div v-else-if="!row.editing" class="audio-placeholder"><span>▶</span><small>{{ row.status === 'generating' ? '正在生成音频…' : '尚未生成音频' }}</small></div>
              <div v-if="row.error" class="row-error" role="alert">{{ row.error }}</div>
              <div class="sentence-actions">
                <template v-if="row.editing"><button type="button" class="outline-button" @click="cancelEdit(row)">取消</button><button type="button" class="primary-button" :disabled="!row.draftText.trim()" @click="saveEdit(row)">保存修改</button></template>
                <template v-else-if="row.accepted"><span class="state-note">已确认句不会被批量生成覆盖</span><button type="button" class="outline-button" @click="toggleAccepted(row)">取消锁定</button></template>
                <template v-else-if="row.status === 'error'"><span class="state-note error">失败只影响本句，其他已完成句子保持不变</span><button type="button" class="outline-button" @click="beginEdit(row)">编辑文本</button><button type="button" class="primary-button" @click="generateSentence(row)">重试本句</button></template>
                <template v-else-if="row.status === 'stale'"><span class="state-note edited">原音频已保留；新版本满意后再替换</span><button type="button" class="outline-button" @click="playRow(row)">查看原音频</button><button type="button" class="primary-button" @click="generateSentence(row)">生成新版本</button></template>
                <template v-else><span class="state-note">不满意可继续生成新版本，不影响其他句子</span><button type="button" class="outline-button" :disabled="row.status === 'generating' || analysisExpired" @click="generateSentence(row)">{{ row.status === 'generating' ? '生成中…' : row.audioBlob ? '重新生成' : '生成此句' }}</button><button v-if="row.audioBlob" type="button" class="primary-button" :disabled="row.status === 'generating'" @click="toggleAccepted(row)">确认此句</button></template>
              </div>
            </li>
            <li v-if="!filteredSentences.length" class="filtered-empty">当前筛选下没有句子</li>
          </ol>
          <p v-if="sentenceFilter === 'pending' && acceptedCount" class="hidden-note">已隐藏 {{ acceptedCount }} 个已确认句 · 切换“已确认”查看</p>
          <section v-if="finalAudioUrl" class="final-result"><div><strong>完整音频已合成</strong><small>{{ sentences.length }} 句 · {{ selectedVoiceLabel }} · {{ languageLabel }} · WAV</small><small v-if="downloadMessage" class="download-message" role="status">{{ downloadMessage }}</small><small v-if="downloadError" class="download-message error" role="alert">{{ downloadError }}</small></div><audio :src="finalAudioUrl" controls preload="metadata" @loadedmetadata="readFinalDuration" /><span><small v-if="finalDuration">总时长 {{ finalDuration }}</small><button type="button" class="outline-button" @click="downloadFinal">下载 WAV</button><button type="button" class="text-action" @click="assembleFinal">重新合成</button></span></section>
        </template>
        <footer v-if="sentences.length" class="final-bar"><div><strong>已确认 {{ acceptedCount }} / {{ sentences.length }}</strong><span>{{ allAccepted ? '所有句子已确认，可以合成完整音频' : '还差 ' + (sentences.length - acceptedCount) + ' 句确认；可先连续试听当前版本' }}</span></div><button type="button" class="outline-button sequence-button" :disabled="!generatedCount" @click="toggleSequence">{{ previewingSequence ? '■ 停止试听' : '▶ 连续试听' }}</button><button type="button" class="primary-button assemble-button" :disabled="!allAccepted || assembling || batchRunning || analysisExpired" @click="assembleFinal">{{ assembling ? '正在合成…' : '合成完整音频' }}</button></footer>
      </section>
    </div>

    <Teleport to="body">
      <div v-if="dictionaryOpen" class="drawer-layer" @keydown.esc="closeDictionary"><button class="scrim" aria-label="关闭发音词典" @click="closeDictionary" /><aside ref="drawer" class="dictionary-drawer" role="dialog" aria-modal="true" aria-labelledby="dictionary-title" tabindex="-1"><header><div><h2 id="dictionary-title">发音词典</h2><p>管理多音字和专有名词读音</p></div><button type="button" aria-label="关闭" @click="closeDictionary">×</button></header><div class="dictionary-toolbar"><input v-model.trim="dictionaryQuery" type="search" placeholder="搜索原文、读音或备注"><button type="button" @click="startCreateEntry">+ 新增词条</button></div><p v-if="dictionaryError" class="drawer-error">{{ dictionaryError }}</p><div v-if="dictionaryLoading" class="dictionary-loading"><span class="spinner" />正在读取词典…</div><div v-else class="dictionary-list"><article v-for="entry in filteredDictionary" :key="entry.id"><div><strong>{{ entry.phrase }}</strong><span>{{ entry.pinyin }}</span><small>{{ entry.note || (entry.source === 'builtin' ? '系统内置规则' : '人工规则') }}</small></div><em>{{ entry.source === 'builtin' ? '内置' : '人工' }}</em><div><button :disabled="!entry.editable" @click="editEntry(entry)">编辑</button><button @click="previewEntry(entry)">试听</button><button class="danger" :disabled="entry.source !== 'manual'" @click="confirmDelete(entry)">删除</button></div></article><p v-if="!filteredDictionary.length" class="dictionary-empty">暂无匹配的发音规则</p></div><form v-if="entryFormOpen" class="entry-form" @submit.prevent="saveEntry"><h3>{{ editingEntry ? '编辑词条' : '新增词条' }}</h3><label>原文<input v-model.trim="entryForm.phrase" required maxlength="120" :disabled="Boolean(editingEntry)"></label><label>读音 / 拼音<input v-model.trim="entryForm.pinyin" required maxlength="240"></label><label>备注<input v-model.trim="entryForm.note" maxlength="500"></label><label class="check"><input v-model="entryForm.enabled" type="checkbox"> 启用该规则</label><div><button type="button" class="outline-button" @click="entryFormOpen = false">取消</button><button type="submit" class="primary-button" :disabled="dictionarySaving">{{ dictionarySaving ? '保存中…' : '保存' }}</button></div></form><section class="dictionary-preview"><h3>发音试听</h3><div><input v-model.trim="previewText" maxlength="500" placeholder="输入要试听的文本"><select v-model="previewVoice"><option v-for="item in availableVoices" :key="item.id" :value="item.id">{{ item.label }}</option></select><button :disabled="!previewText || !previewVoice || previewingDictionary" @click="previewDictionaryText">{{ previewingDictionary ? '生成中…' : '试听发音' }}</button></div></section><footer><span>内置规则不可删除；人工覆盖删除后恢复内置读音。</span><button class="primary-button" @click="closeDictionary">完成</button></footer></aside></div>
      <div v-if="deleteTarget" class="modal-layer"><section><h2>删除发音词条？</h2><p>将删除「{{ deleteTarget.phrase }}」的人工规则。历史数据不会被删除。</p><div><button class="outline-button" @click="deleteTarget = null">取消</button><button class="danger-button" :disabled="dictionarySaving" @click="deleteEntry">确认删除</button></div></section></div>
      <div v-if="leaveDialogOpen" class="modal-layer"><section><h2>音频制作尚未完成</h2><p>离开页面后，当前未保存的单句音频和制作进度可能丢失。</p><div><button class="outline-button" @click="continueEditing">继续制作</button><button class="primary-button" @click="confirmLeave">确认离开</button></div></section></div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, type NavigationGuardNext } from 'vue-router'
import { cabinlingoApi, type TTSOptions, type TTSPronunciationEntry, type TTSProsodyAnalysisSegment, type TTSProsodyScene, type TTSProsodySegment, type TTSVoiceOption } from '@/api'
import { useSessionStore } from '@/stores/session'
import { deleteProsodyProject, loadProsodyProject, saveProsodyProject } from '@/utils/prosodyProjectStore'

type SentenceStatus = 'idle' | 'generating' | 'ready' | 'accepted' | 'error' | 'stale'
interface SentenceRow { id: string; index: number; text: string; draftText: string; tone: string; pace: string; intonation: 'rise' | 'fall' | 'level'; pitch: number; energy: number; pauseAfterMs: number; emphasis: string[]; emphasisDraft: string; status: SentenceStatus; version: number; audioBlob: Blob | null; audioUrl: string; accepted: boolean; editing: boolean; error: string }
type StoredSentenceRow = Omit<SentenceRow, 'audioUrl' | 'editing'>
interface StoredProsodyProject { version: 1; savedAt: string; text: string; scene: string; language: 'zh' | 'en'; voice: string; rate: number; analysisSource: { text: string; scene: string }; sentences: StoredSentenceRow[]; finalAudioBlob: Blob | null; finalDuration: string }

const DRAFT_KEY = 'cabinlingo_prosody_studio_draft_v2'
const session = useSessionStore()
const toneOptions = ['亲切', '平稳', '提醒', '关切', '严肃', '紧迫', '明确']
const paceOptions = ['稍慢', '中速', '稍快']
const options = ref<TTSOptions | null>(null)
const scenes = ref<TTSProsodyScene[]>([])
const scene = ref('')
const text = ref('')
const language = ref<'zh' | 'en'>('zh')
const voice = ref('')
const rate = ref(1)
const sentences = ref<SentenceRow[]>([])
const analysisSource = ref({ text: '', scene: '' })
const bootstrapLoading = ref(true)
const analyzing = ref(false)
const assembling = ref(false)
const previewingVoice = ref(false)
const serviceError = ref('')
const fieldError = ref('')
const operationError = ref<{ title: string; message: string } | null>(null)
const savedAt = ref('')
const finalAudioBlob = ref<Blob | null>(null)
const finalAudioUrl = ref('')
const finalDuration = ref('')
const downloadMessage = ref('')
const downloadError = ref('')
const projectSaving = ref(false)
const projectSavedAt = ref('')
const projectDirty = ref(false)
const recoveryMessage = ref('')
const storageError = ref('')
const batchRunning = ref(false)
const batchTotal = ref(0)
const batchFinished = ref(0)
const batchSuccess = ref(0)
const batchFailed = ref(0)
const textInput = ref<HTMLTextAreaElement | null>(null)
const resultsPanel = ref<HTMLElement | null>(null)
const voicePreviewPlayer = ref<HTMLAudioElement | null>(null)
const voicePreviewUrl = ref('')
const voicePreviewHint = ref('')
const voicePreviewError = ref('')
const dictionaryOpen = ref(false)
const drawer = ref<HTMLElement | null>(null)
const dictionaryEntries = ref<TTSPronunciationEntry[]>([])
const dictionaryLoading = ref(false)
const dictionarySaving = ref(false)
const dictionaryError = ref('')
const dictionaryQuery = ref('')
const entryFormOpen = ref(false)
const editingEntry = ref<TTSPronunciationEntry | null>(null)
const entryForm = reactive({ phrase: '', pinyin: '', note: '', enabled: true, priority: 100 })
const deleteTarget = ref<TTSPronunciationEntry | null>(null)
const previewText = ref('')
const previewVoice = ref('')
const previewingDictionary = ref(false)
const leaveDialogOpen = ref(false)
type SentenceFilter = 'pending' | 'all' | 'accepted' | 'error' | 'edited'
type VoiceCategory = 'favorite' | 'female' | 'male' | 'scene'
const FAVORITES_KEY = 'cabinlingo_voice_favorites_v1'
const sentenceFilter = ref<SentenceFilter>('pending')
const voiceSelectorOpen = ref(false)
const voiceQuery = ref('')
const voiceCategory = ref<VoiceCategory>('female')
const voiceScene = ref('cabin')
const favoriteVoiceIds = ref<string[]>([])
const previewingVoiceId = ref('')
const previewingSequence = ref(false)
const voiceCategories: Array<{ id: VoiceCategory; label: string }> = [
  { id: 'favorite', label: '我的收藏' }, { id: 'female', label: '女声' },
  { id: 'male', label: '男声' }, { id: 'scene', label: '场景' },
]
const voiceScenes = [
  { id: 'cabin', label: '客舱广播' }, { id: 'service', label: '服务' },
  { id: 'safety', label: '安全提醒' }, { id: 'emergency', label: '应急' },
]
let pendingLeave: NavigationGuardNext | null = null
let returnFocus: HTMLElement | null = null
let saveTimer = 0
let projectSaveTimer = 0
let projectHydrated = false
let projectSaveRequest: Promise<void> | null = null
let settingsReady = false
let sequencePlayer: HTMLAudioElement | null = null

const maxTextChars = computed(() => options.value?.max_text_chars || 10000)
const rateControl = computed(() => options.value?.rate_control || { min: .5, max: 2, step: .05, default: 1, recommended_min: .8, recommended_max: 1.2 })
const availableVoices = computed(() => (options.value?.voices || []).filter(item => item.languages.includes(language.value)))
const selectedVoiceLabel = computed(() => availableVoices.value.find(item => item.id === voice.value)?.label || voice.value)
const languageLabel = computed(() => options.value?.languages.find(item => item.id === language.value)?.label || language.value)
const serviceReady = computed(() => Boolean(options.value?.enabled && scenes.value.length && !serviceError.value))
const canAnalyze = computed(() => serviceReady.value && Boolean(text.value.trim() && scene.value) && text.value.length <= maxTextChars.value)
const analysisExpired = computed(() => Boolean(sentences.value.length && (analysisSource.value.text !== text.value.trim() || analysisSource.value.scene !== scene.value)))
const generatedCount = computed(() => sentences.value.filter(item => item.audioBlob).length)
const acceptedCount = computed(() => sentences.value.filter(item => item.accepted).length)
const allAccepted = computed(() => Boolean(sentences.value.length && acceptedCount.value === sentences.value.length))
const missingCount = computed(() => sentences.value.filter(item => !item.audioBlob || item.status === 'stale' || item.status === 'error').length)
const dictionaryCount = computed(() => dictionaryEntries.value.length || options.value?.pronunciation?.builtin_count || 0)
const filteredDictionary = computed(() => { const query = dictionaryQuery.value.toLocaleLowerCase(); return dictionaryEntries.value.filter(item => !query || [item.phrase, item.pinyin, item.note].some(value => String(value || '').toLocaleLowerCase().includes(query))) })
const workspaceSubtitle = computed(() => sentences.value.length ? `${scenes.value.find(item => item.id === analysisSource.value.scene)?.label || analysisSource.value.scene} · 逐句试听并确认` : '每句独立生成，不满意可单独修改')
const projectStorageKey = computed(() => session.user?.id ? 'prosody-current:' + session.user.id : '')
const hasUnsavedAudio = computed(() => projectDirty.value || projectSaving.value)
const selectedSceneLabel = computed(() => scenes.value.find(item => item.id === scene.value)?.label || scene.value)
const selectedVoice = computed(() => availableVoices.value.find(item => item.id === voice.value))
const selectedVoiceDescription = computed(() => selectedVoice.value ? voiceDescription(selectedVoice.value) : '请选择用于后续生成的音色')
const rateChoices = computed(() => {
  const values = options.value?.rates?.length ? options.value.rates : [.75, .9, 1, 1.1, 1.25]
  return [...new Set([...values, rate.value])].sort((a, b) => a - b)
})
const pendingCount = computed(() => sentences.value.filter(item => !item.accepted && item.status !== 'error').length)
const failedCount = computed(() => sentences.value.filter(item => item.status === 'error').length)
const editedCount = computed(() => sentences.value.filter(item => item.status === 'stale').length)
const filteredSentences = computed(() => sentences.value.filter(row => {
  if (sentenceFilter.value === 'accepted') return row.accepted
  if (sentenceFilter.value === 'error') return row.status === 'error'
  if (sentenceFilter.value === 'edited') return row.status === 'stale'
  if (sentenceFilter.value === 'pending') return !row.accepted
  return true
}))
const sentenceFilters = computed(() => [
  { id: 'pending' as SentenceFilter, label: '仅看待处理', count: sentences.value.length - acceptedCount.value },
  { id: 'all' as SentenceFilter, label: '全部', count: sentences.value.length },
  { id: 'accepted' as SentenceFilter, label: '已确认', count: acceptedCount.value },
  { id: 'error' as SentenceFilter, label: '失败', count: failedCount.value },
  { id: 'edited' as SentenceFilter, label: '已修改', count: editedCount.value },
])
const filteredVoices = computed(() => {
  const query = voiceQuery.value.toLocaleLowerCase()
  return availableVoices.value.filter(item => {
    if (voiceCategory.value === 'favorite' && !isFavorite(item.id)) return false
    if (voiceCategory.value === 'female' && item.gender !== 'female') return false
    if (voiceCategory.value === 'male' && item.gender !== 'male') return false
    const haystack = [item.label, item.trait, item.category, item.source].filter(Boolean).join(' ').toLocaleLowerCase()
    if (voiceCategory.value === 'scene') {
      const terms: Record<string, string[]> = {
        cabin: ['客舱', '广播', 'cabin'], service: ['服务', '亲切', 'service'],
        safety: ['安全', '提醒', '沉稳', 'safety'], emergency: ['应急', '紧迫', 'emergency'],
      }
      if (!(terms[voiceScene.value] || []).some(term => haystack.includes(term))) return false
    }
    return !query || haystack.includes(query)
  })
})

watch(language, () => { if (!availableVoices.value.some(item => item.id === voice.value)) voice.value = availableVoices.value[0]?.id || ''; previewVoice.value = voice.value })
watch([language, voice, rate], () => { clearVoicePreview(); if (settingsReady) invalidateAllAudio() })
watch([text, scene, language, voice, rate], () => { window.clearTimeout(saveTimer); saveTimer = window.setTimeout(saveDraft, 400) })
watch([text, scene, language, voice, rate, analysisSource, sentences, finalAudioBlob, finalDuration], () => { if (projectHydrated) queueProjectSave() }, { deep: true })

function saveDraft() { sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ text: text.value, scene: scene.value, language: language.value, voice: voice.value, rate: rate.value })); savedAt.value = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date()) }
function restoreDraft() { try { const draft = JSON.parse(sessionStorage.getItem(DRAFT_KEY) || '{}'); text.value = typeof draft.text === 'string' ? draft.text : ''; scene.value = typeof draft.scene === 'string' ? draft.scene : ''; language.value = draft.language === 'en' ? 'en' : 'zh'; voice.value = typeof draft.voice === 'string' ? draft.voice : ''; rate.value = Number.isFinite(Number(draft.rate)) ? Number(draft.rate) : 1 } catch { sessionStorage.removeItem(DRAFT_KEY) } }
function queueProjectSave(delay = 700) {
  if (!projectHydrated) return
  projectDirty.value = true
  window.clearTimeout(projectSaveTimer)
  projectSaveTimer = window.setTimeout(() => { projectSaveTimer = 0; void persistProject() }, delay)
}
function projectSnapshot(): StoredProsodyProject {
  return {
    version: 1,
    savedAt: new Date().toISOString(),
    text: text.value,
    scene: scene.value,
    language: language.value,
    voice: voice.value,
    rate: rate.value,
    analysisSource: { ...analysisSource.value },
    sentences: sentences.value.map(row => ({
      id: row.id, index: row.index, text: row.text, draftText: row.draftText,
      tone: row.tone, pace: row.pace, intonation: row.intonation,
      pitch: row.pitch, energy: row.energy, pauseAfterMs: row.pauseAfterMs,
      emphasis: [...row.emphasis], emphasisDraft: row.emphasisDraft,
      status: row.status, version: row.version, audioBlob: row.audioBlob,
      accepted: row.accepted, error: row.error,
    })),
    finalAudioBlob: finalAudioBlob.value,
    finalDuration: finalDuration.value,
  }
}
async function persistProject(): Promise<void> {
  if (!projectHydrated || !projectStorageKey.value) return
  window.clearTimeout(projectSaveTimer); projectSaveTimer = 0
  if (projectSaveRequest) {
    await projectSaveRequest
    if (projectDirty.value) await persistProject()
    return
  }
  const key = projectStorageKey.value
  const snapshot = projectSnapshot()
  projectDirty.value = false
  projectSaving.value = true
  storageError.value = ''
  const request = (snapshot.text.trim() || snapshot.sentences.length || snapshot.finalAudioBlob)
    ? saveProsodyProject(key, snapshot)
    : deleteProsodyProject(key)
  projectSaveRequest = request
  try {
    await request
    projectSavedAt.value = snapshot.text.trim() || snapshot.sentences.length || snapshot.finalAudioBlob
      ? new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date(snapshot.savedAt))
      : ''
  } catch {
    projectDirty.value = true
    storageError.value = '制作记录未能保存到本机。请勿刷新或离开页面，并检查浏览器是否禁用了网站存储。'
  } finally {
    if (projectSaveRequest === request) projectSaveRequest = null
    projectSaving.value = false
    if (projectDirty.value && !storageError.value) queueProjectSave(150)
  }
}
async function restoreProjectDraft() {
  if (!projectStorageKey.value) return
  try {
    const project = await loadProsodyProject<StoredProsodyProject>(projectStorageKey.value)
    if (!project || project.version !== 1) return
    text.value = project.text || ''
    scene.value = project.scene || ''
    language.value = project.language === 'en' ? 'en' : 'zh'
    voice.value = project.voice || ''
    rate.value = Number.isFinite(project.rate) ? project.rate : 1
    analysisSource.value = project.analysisSource || { text: '', scene: '' }
    sentences.value = Array.isArray(project.sentences) ? project.sentences.map(row => {
      const audioBlob = row.audioBlob instanceof Blob ? row.audioBlob : null
      const status = row.status === 'generating' ? (audioBlob ? 'ready' : 'idle') : row.status
      return { ...row, status, audioBlob, audioUrl: audioBlob ? URL.createObjectURL(audioBlob) : '', accepted: Boolean(row.accepted && audioBlob), editing: false }
    }) : []
    if (project.finalAudioBlob instanceof Blob) {
      finalAudioBlob.value = project.finalAudioBlob
      finalAudioUrl.value = URL.createObjectURL(project.finalAudioBlob)
      finalDuration.value = project.finalDuration || ''
    }
    projectSavedAt.value = project.savedAt ? new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date(project.savedAt)) : ''
    const restoredAudio = sentences.value.filter(row => row.audioBlob).length
    recoveryMessage.value = '已恢复上次本机制作记录：' + sentences.value.length + ' 句，' + restoredAudio + ' 句含音频' + (finalAudioBlob.value ? '，完整音频也已恢复。' : '。')
  } catch {
    storageError.value = '无法读取本机制作记录；当前页面仍可使用，但刷新或离开前请先下载音频。'
  }
}
async function clearPersistedProject() {
  window.clearTimeout(projectSaveTimer); projectSaveTimer = 0
  try {
    if (projectSaveRequest) await projectSaveRequest.catch(() => undefined)
    if (projectStorageKey.value) await deleteProsodyProject(projectStorageKey.value)
    projectDirty.value = false; projectSavedAt.value = ''; recoveryMessage.value = ''; storageError.value = ''
  } catch { storageError.value = '本机制作记录未能清除，请检查浏览器网站存储设置。' }
}
function voiceMeta(item: TTSVoiceOption) { const values = [item.gender === 'female' ? '女声' : item.gender === 'male' ? '男声' : '', item.trait]; return values.some(Boolean) ? ` · ${values.filter(Boolean).join(' · ')}` : '' }
function voiceDescription(item: TTSVoiceOption) {
  const gender = item.gender === 'female' ? '女声' : item.gender === 'male' ? '男声' : ''
  return [item.trait, item.category, gender].filter(Boolean).slice(0, 2).join(' · ') || '通用播报音色'
}
function isFavorite(id: string) { return Boolean(id && favoriteVoiceIds.value.includes(id)) }
function toggleFavorite(id: string) {
  favoriteVoiceIds.value = isFavorite(id) ? favoriteVoiceIds.value.filter(item => item !== id) : [...favoriteVoiceIds.value, id]
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(favoriteVoiceIds.value))
}
function restoreFavorites() {
  try {
    const value = JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]')
    favoriteVoiceIds.value = Array.isArray(value) ? value.filter(item => typeof item === 'string') : []
  } catch { localStorage.removeItem(FAVORITES_KEY) }
}
function selectVoice(item: TTSVoiceOption) { voice.value = item.id; voiceSelectorOpen.value = false }
function restartSource() {
  stopSequence()
  sentences.value.forEach(revokeRow)
  sentences.value = []
  analysisSource.value = { text: '', scene: '' }
  sentenceFilter.value = 'pending'
  operationError.value = null
  clearFinal()
  queueProjectSave(0)
  nextTick(() => textInput.value?.focus())
}
function validateText() { fieldError.value = !text.value.trim() ? '请输入播报文本。' : text.value.length > maxTextChars.value ? `文本不能超过 ${maxTextChars.value} 字。` : '' }
function pitchLabel(value: number) { return value < 0 ? '中低音' : value > 0 ? '中高音' : '中音' }
function defaultTone() { return ({ general: '平稳', medical_help: '关切', emergency: '紧迫', service: '亲切' } as Record<string, string>)[scene.value] || '平稳' }
function paceFrom(segment: TTSProsodyAnalysisSegment) { return segment.rate < .97 ? '稍慢' : segment.rate > 1.03 ? '稍快' : '中速' }
function pausePreset(value: number) { return [0, 200, 400, 700].includes(value) ? String(value) : 'custom' }
function pauseMarker(value: number) { return value === 0 ? '无' : value === 200 ? '/' : value === 400 ? '//' : value === 700 ? '///' : '自定义' }
function applyPausePreset(row: SentenceRow, event: Event) { const value = (event.target as HTMLSelectElement).value; if (value !== 'custom') row.pauseAfterMs = Number(value) }
function usesProsodyNotation(value: string) { return /^\s*\[(亲切|平稳|提醒|关切|严肃|紧迫|明确|稍慢|中速|稍快)\]/m.test(value) || /【[^【】]+】/.test(value) || /(?:\/\/\/|\/\/|\/)\s*[↑↓→]?\s*$/m.test(value) || /[↑↓→]\s*$/m.test(value) }
function statusLabel(row: SentenceRow) { if (row.accepted) return '已确认'; return ({ idle: '待生成', generating: row.audioBlob ? '重新生成中' : '生成中', ready: '待确认', accepted: '已确认', error: '生成失败', stale: '需要重新生成' } as Record<SentenceStatus, string>)[row.status] }
function revokeRow(row: SentenceRow) { if (row.audioUrl) URL.revokeObjectURL(row.audioUrl); row.audioUrl = ''; row.audioBlob = null }
function clearFinal() { if (finalAudioUrl.value) URL.revokeObjectURL(finalAudioUrl.value); finalAudioUrl.value = ''; finalAudioBlob.value = null; finalDuration.value = ''; downloadMessage.value = ''; downloadError.value = '' }
function clearVoicePreview() { voicePreviewPlayer.value?.pause(); if (voicePreviewUrl.value) URL.revokeObjectURL(voicePreviewUrl.value); voicePreviewUrl.value = ''; voicePreviewHint.value = ''; voicePreviewError.value = '' }
function invalidateAllAudio() { clearFinal(); sentences.value.forEach(row => { if (row.audioBlob) row.status = 'stale'; row.accepted = false }) }
async function clearText() { sentences.value.forEach(revokeRow); sentences.value = []; text.value = ''; analysisSource.value = { text: '', scene: '' }; operationError.value = null; fieldError.value = ''; clearFinal(); await clearPersistedProject(); nextTick(() => textInput.value?.focus()) }

async function loadInitial() {
  bootstrapLoading.value = true; serviceError.value = ''
  const [optionsResult, scenesResult] = await Promise.allSettled([cabinlingoApi.ttsOptions(), cabinlingoApi.prosodyScenes()])
  if (optionsResult.status === 'fulfilled') options.value = optionsResult.value
  if (scenesResult.status === 'fulfilled') scenes.value = scenesResult.value.scenes
  if (optionsResult.status === 'rejected' || scenesResult.status === 'rejected') serviceError.value = apiMessage(optionsResult.status === 'rejected' ? optionsResult.reason : (scenesResult as PromiseRejectedResult).reason, '无法读取 TTS / Prosody 配置，请检查网络、权限或服务状态。')
  restoreDraft()
  if (!session.user) await session.restore().catch(() => false)
  await restoreProjectDraft()
  if (!scenes.value.some(item => item.id === scene.value)) scene.value = scenes.value.find(item => item.id === 'general')?.id || scenes.value[0]?.id || ''
  if (!availableVoices.value.some(item => item.id === voice.value)) voice.value = availableVoices.value[0]?.id || ''
  previewVoice.value = voice.value; bootstrapLoading.value = false; await nextTick(); settingsReady = true; projectHydrated = true
}

async function analyze() {
  validateText(); if (!canAnalyze.value || fieldError.value) { textInput.value?.focus(); return }
  analyzing.value = true; operationError.value = null; clearFinal()
  try {
    const source = { text: text.value.trim(), scene: scene.value }
    sentences.value.forEach(revokeRow)
    if (usesProsodyNotation(source.text)) {
      const result = await cabinlingoApi.previewProsodyTts(source.text, language.value)
      const profile = scenes.value.find(item => item.id === scene.value)
      sentences.value = result.segments.map((segment: TTSProsodySegment, index: number) => ({ id: `${Date.now()}-${index}`, index, text: segment.text, draftText: segment.text, tone: segment.tone || defaultTone(), pace: segment.pace || '中速', intonation: segment.intonation || (/[？?]$/.test(segment.text) ? 'rise' : 'fall'), pitch: profile?.pitch || 0, energy: profile?.energy || 1, pauseAfterMs: segment.pause_after_ms, emphasis: [...segment.emphasis], emphasisDraft: segment.emphasis.join('、'), status: 'idle', version: 0, audioBlob: null, audioUrl: '', accepted: false, editing: false, error: '' }))
    } else {
      const result = await cabinlingoApi.analyzeProsody(source)
      sentences.value = result.segments.map(segment => ({ id: `${Date.now()}-${segment.index}`, index: segment.index, text: segment.text, draftText: segment.text, tone: defaultTone(), pace: paceFrom(segment), intonation: /[？?]$/.test(segment.text) ? 'rise' : 'fall', pitch: segment.pitch, energy: segment.energy, pauseAfterMs: segment.pause_after_ms, emphasis: [...segment.emphasis], emphasisDraft: segment.emphasis.join('、'), status: 'idle', version: 0, audioBlob: null, audioUrl: '', accepted: false, editing: false, error: '' }))
    }
    analysisSource.value = source; batchTotal.value = 0; await nextTick(); resultsPanel.value?.focus()
  } catch (error) { operationError.value = classifyError(error, '语调分析失败') }
  finally { analyzing.value = false }
}

function buildSentenceScript(row: SentenceRow) {
  let content = row.text
  for (const word of [...row.emphasis].sort((a, b) => b.length - a.length)) { const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); content = content.replace(new RegExp(escaped, 'g'), match => `【${match}】`) }
  const arrow = row.intonation === 'rise' ? '↑' : row.intonation === 'level' ? '→' : '↓'
  return `[${row.tone}][${row.pace}]${content} ${arrow}`
}

async function generateSentence(row: SentenceRow, fromBatch = false) {
  if (!voice.value || analysisExpired.value || row.status === 'generating') return false
  const settingsSignature = `${language.value}:${voice.value}:${rate.value}`
  row.status = 'generating'; row.error = ''; row.accepted = false; clearFinal()
  try {
    const blob = await cabinlingoApi.generateProsodyTts({ script: buildSentenceScript(row), language: language.value, voice: voice.value, base_rate: rate.value })
    revokeRow(row); row.audioBlob = blob; row.audioUrl = URL.createObjectURL(blob); row.version += 1
    row.status = settingsSignature === `${language.value}:${voice.value}:${rate.value}` ? 'ready' : 'stale'
    if (fromBatch) batchSuccess.value += 1
    return true
  } catch (error) { row.status = 'error'; row.error = classifyError(error, '音频生成失败').message; if (fromBatch) batchFailed.value += 1; return false }
  finally { if (fromBatch) batchFinished.value += 1 }
}

async function generateBatch(onlyMissing: boolean) {
  const queue = sentences.value.filter(row => row.status !== 'generating' && (!onlyMissing || !row.audioBlob || row.status === 'stale' || row.status === 'error'))
  if (!queue.length) return
  batchRunning.value = true; batchTotal.value = queue.length; batchFinished.value = 0; batchSuccess.value = 0; batchFailed.value = 0
  let cursor = 0
  const worker = async () => { while (cursor < queue.length) { const row = queue[cursor++]; await generateSentence(row, true) } }
  await Promise.all([worker(), worker()]); batchRunning.value = false
}

function beginEdit(row: SentenceRow) { row.draftText = row.text; row.emphasisDraft = row.emphasis.join('、'); row.editing = true }
function cancelEdit(row: SentenceRow) { row.draftText = row.text; row.emphasisDraft = row.emphasis.join('、'); row.editing = false; row.error = '' }
function saveEdit(row: SentenceRow) {
  const next = row.draftText.trim()
  if (!next) return
  const emphasis = [...new Set(row.emphasisDraft.split(/[、,，;；\n]+/).map(item => item.trim()).filter(Boolean))]
  if (emphasis.length > 8) { row.error = '每句话最多设置 8 个重音词。'; return }
  const missing = emphasis.filter(item => !next.includes(item))
  if (missing.length) { row.error = `重音词未出现在本句正文中：${missing.join('、')}`; return }
  row.text = next; row.emphasis = emphasis; row.emphasisDraft = emphasis.join('、'); row.accepted = false; row.status = row.audioBlob ? 'stale' : 'idle'; row.error = ''; row.editing = false; clearFinal()
}
function toggleAccepted(row: SentenceRow) { if (!row.audioBlob || row.status === 'stale') return; row.accepted = !row.accepted; row.status = row.accepted ? 'accepted' : 'ready'; clearFinal() }

async function assembleFinal() {
  if (!allAccepted.value) return
  assembling.value = true; operationError.value = null
  try {
    const clips = sentences.value.map(row => row.audioBlob as Blob)
    const manifest = sentences.value.map((row, index) => ({ index, pause_after_ms: index === sentences.value.length - 1 ? 0 : row.pauseAfterMs }))
    const blob = await cabinlingoApi.assembleProsodyTts(clips, manifest)
    clearFinal(); finalAudioBlob.value = blob; finalAudioUrl.value = URL.createObjectURL(blob)
  } catch (error) { operationError.value = classifyError(error, '完整音频合成失败') }
  finally { assembling.value = false }
}

function readFinalDuration(event: Event) { const seconds = (event.target as HTMLAudioElement).duration; if (Number.isFinite(seconds)) finalDuration.value = `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}` }
function downloadFinal() {
  if (!finalAudioBlob.value || !finalAudioUrl.value) return
  const filename = 'CabinLingo-Prosody-' + new Date().toISOString().replace(/[:.]/g, '-') + '.wav'
  downloadMessage.value = ''; downloadError.value = ''
  try {
    const attachment = new Blob([finalAudioBlob.value], { type: 'application/octet-stream' })
    const downloadUrl = URL.createObjectURL(attachment)
    const link = document.createElement('a')
    link.href = downloadUrl; link.download = filename; link.style.display = 'none'
    document.body.appendChild(link); link.click(); link.remove()
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 60_000)
    downloadMessage.value = '已提交下载：' + filename + '。可在浏览器下载列表中查看进度和保存位置。'
  } catch {
    downloadError.value = '下载未启动，完整音频仍保存在本机制作记录中，请重试。'
  }
}
async function previewSelectedVoice() { if (!voice.value || previewingVoice.value) return; const requested = voice.value; previewingVoice.value = true; clearVoicePreview(); try { const sample = language.value === 'zh' ? '欢迎使用 CabinLingo 智能音频制作。' : 'Welcome to CabinLingo audio studio.'; const blob = await cabinlingoApi.generateTts({ text: sample, language: language.value, voice: requested, rate: 1, format: 'mp3' }); if (voice.value !== requested) return; voicePreviewUrl.value = URL.createObjectURL(blob); voicePreviewHint.value = '试听已生成，正在准备播放…'; await nextTick(); try { await voicePreviewPlayer.value?.play(); voicePreviewHint.value = '正在播放试听音频' } catch { voicePreviewHint.value = '试听已生成，请点击右侧播放按钮' } } catch (error) { voicePreviewError.value = apiMessage(error, '音色试听生成失败，请检查音色、服务额度或网络。') } finally { previewingVoice.value = false } }
async function previewVoiceOption(item: TTSVoiceOption) {
  if (previewingVoice.value) return
  previewingVoice.value = true
  previewingVoiceId.value = item.id
  clearVoicePreview()
  try {
    const sample = language.value === 'zh' ? '欢迎使用 CabinLingo 智能音频制作。' : 'Welcome to CabinLingo audio studio.'
    const blob = await cabinlingoApi.generateTts({ text: sample, language: language.value, voice: item.id, rate: 1, format: 'mp3' })
    voicePreviewUrl.value = URL.createObjectURL(blob)
    voicePreviewHint.value = item.label + ' · 试听已生成'
    await nextTick()
    try { await voicePreviewPlayer.value?.play() } catch { voicePreviewHint.value += '，请点击播放按钮' }
  } catch (error) { voicePreviewError.value = apiMessage(error, '音色试听生成失败，请检查音色、服务额度或网络。') }
  finally { previewingVoice.value = false; previewingVoiceId.value = '' }
}
function playRow(row: SentenceRow) { if (row.audioUrl) void new Audio(row.audioUrl).play() }
function stopSequence() {
  sequencePlayer?.pause()
  sequencePlayer = null
  previewingSequence.value = false
}
async function toggleSequence() {
  if (previewingSequence.value) { stopSequence(); return }
  const urls = sentences.value.map(row => row.audioUrl).filter(Boolean)
  if (!urls.length) return
  previewingSequence.value = true
  for (const url of urls) {
    if (!previewingSequence.value) break
    sequencePlayer = new Audio(url)
    try {
      await sequencePlayer.play()
      await new Promise<void>(resolve => {
        if (!sequencePlayer) return resolve()
        sequencePlayer.onended = () => resolve()
        sequencePlayer.onerror = () => resolve()
      })
    } catch { break }
  }
  stopSequence()
}

async function openDictionary(event: Event) { returnFocus = event.currentTarget as HTMLElement; dictionaryOpen.value = true; await nextTick(); drawer.value?.focus(); await loadDictionary() }
function closeDictionary() { dictionaryOpen.value = false; entryFormOpen.value = false; deleteTarget.value = null; nextTick(() => returnFocus?.focus()) }
async function loadDictionary() { dictionaryLoading.value = true; dictionaryError.value = ''; try { dictionaryEntries.value = (await cabinlingoApi.ttsPronunciations()).items } catch (error) { dictionaryError.value = apiMessage(error, '发音词典读取失败。') } finally { dictionaryLoading.value = false } }
function startCreateEntry() { editingEntry.value = null; Object.assign(entryForm, { phrase: '', pinyin: '', note: '', enabled: true, priority: 100 }); entryFormOpen.value = true }
function editEntry(entry: TTSPronunciationEntry) { editingEntry.value = entry; Object.assign(entryForm, { phrase: entry.phrase, pinyin: entry.pinyin, note: entry.note || '', enabled: entry.enabled, priority: entry.priority || 100 }); entryFormOpen.value = true }
async function saveEntry() { dictionarySaving.value = true; dictionaryError.value = ''; try { await cabinlingoApi.saveTtsPronunciation({ ...entryForm }); await loadDictionary(); entryFormOpen.value = false } catch (error) { dictionaryError.value = apiMessage(error, '发音规则保存失败。') } finally { dictionarySaving.value = false } }
function confirmDelete(entry: TTSPronunciationEntry) { if (entry.source === 'manual') deleteTarget.value = entry }
async function deleteEntry() { if (!deleteTarget.value) return; dictionarySaving.value = true; try { await cabinlingoApi.deleteTtsPronunciation(deleteTarget.value.id); deleteTarget.value = null; await loadDictionary() } catch (error) { dictionaryError.value = apiMessage(error, '发音规则删除失败。'); deleteTarget.value = null } finally { dictionarySaving.value = false } }
async function previewEntry(entry: TTSPronunciationEntry) { previewText.value = entry.phrase; await previewDictionaryText() }
async function previewDictionaryText() { if (!previewText.value || !previewVoice.value) return; previewingDictionary.value = true; dictionaryError.value = ''; try { const preview = await cabinlingoApi.previewTtsPronunciation(previewText.value, language.value); const blob = await cabinlingoApi.generateTts({ text: previewText.value, language: language.value, voice: previewVoice.value, rate: 1, format: 'mp3', pronunciations: preview.items.map(item => ({ phrase: item.phrase, pinyin: item.pinyin, applied: item.applied })) }); const url = URL.createObjectURL(blob); const player = new Audio(url); player.onended = () => URL.revokeObjectURL(url); player.onerror = () => URL.revokeObjectURL(url); await player.play() } catch (error) { dictionaryError.value = apiMessage(error, '发音试听失败，请检查规则、音色和服务状态。') } finally { previewingDictionary.value = false } }

function apiMessage(error: any, fallback: string) { const detail = error?.response?.data?.detail; if (Array.isArray(detail)) return detail.map((item: any) => item.msg || String(item)).join('；'); return typeof detail === 'string' ? detail : fallback }
function classifyError(error: any, title: string) { const status = error?.response?.status; if (status === 422) return { title: '字段校验失败', message: apiMessage(error, '请检查文本、音频片段和声音参数。') }; if (status === 401 || status === 403) return { title: '权限验证失败', message: '当前会话无权使用该能力，请重新登录或联系管理员。' }; if (status === 503) return { title: '服务不可用', message: apiMessage(error, '语音服务暂不可用，请稍后重试。') }; if (!error?.response || error?.code === 'ECONNABORTED') return { title: '服务连接超时', message: '未收到服务响应，草稿已保留，请稍后重试。' }; return { title, message: apiMessage(error, '服务暂时无法完成请求，请稍后重试。') } }
function beforeUnload(event: BeforeUnloadEvent) { if (hasUnsavedAudio.value) { event.preventDefault(); event.returnValue = '' } }
function continueEditing() { leaveDialogOpen.value = false; pendingLeave?.(false); pendingLeave = null }
function confirmLeave() { leaveDialogOpen.value = false; const next = pendingLeave; pendingLeave = null; next?.() }
onBeforeRouteLeave((_to, _from, next) => { if (!hasUnsavedAudio.value) return next(); pendingLeave = next; leaveDialogOpen.value = true })
onMounted(() => { restoreFavorites(); window.addEventListener('beforeunload', beforeUnload); loadInitial() })
onBeforeUnmount(() => { projectHydrated = false; stopSequence(); window.clearTimeout(saveTimer); window.clearTimeout(projectSaveTimer); window.removeEventListener('beforeunload', beforeUnload); sentences.value.forEach(revokeRow); clearFinal(); clearVoicePreview() })
</script>

<style scoped>
.prosody-studio{--blue:#1a4ff0;--ink:#12141a;--muted:#666873;--line:#e5ebf2;--soft:#f6faff;min-width:0;color:var(--ink)}button,select,textarea,input{font:inherit}button{border:0;cursor:pointer}.studio-intro{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin:-14px 0 20px}.studio-intro h1{margin:0;font-size:23px}.studio-intro p{margin:6px 0 0;color:var(--muted);font-size:12px}.service-meta{display:grid;justify-items:end;gap:6px}.service-meta small{color:#8992a3;font-size:10px}.service-pill{display:flex;align-items:center;gap:7px;padding:7px 10px;border-radius:999px;font-size:10px;font-weight:700}.service-pill i{width:7px;height:7px;border-radius:50%;background:currentColor}.service-pill.ready{color:#178663;background:#eaf8f2}.service-pill.unavailable{color:#bd554c;background:#fff0ed}.studio-grid{display:grid;grid-template-columns:minmax(330px,410px) minmax(520px,1fr);gap:20px;align-items:start}.card{min-width:0;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:0 6px 18px #0a1a380d}.settings-card{padding:22px}.card-title,.workspace-heading,.field-row,.batch-toolbar,.sentence-top,.sentence-actions,.final-bar,.final-result{display:flex;align-items:center;justify-content:space-between;gap:12px}.card-title{align-items:flex-start;margin-bottom:18px}.card-title h2,.workspace-heading h2{margin:0;font-size:17px}.card-title p,.workspace-heading p{margin:5px 0 0;color:#858995;font-size:11px}.link-button,.text-action{padding:4px;color:var(--blue);background:transparent;font-size:11px}.field-label{display:block;margin:14px 0 7px;color:#4c5060;font-size:11px;font-weight:700}.field-row>span:last-child{color:#8d93a1;font-size:10px}.settings-card select,.settings-card textarea,.sentence-editor,.sentence-controls select,.sentence-controls input,.dictionary-drawer input,.dictionary-drawer select,.entry-form input{width:100%;box-sizing:border-box;border:1px solid #d8e0ea;border-radius:10px;color:#252934;background:#fff;outline:none}.settings-card select{height:44px;padding:0 11px}.settings-card textarea{min-height:205px;padding:12px;resize:vertical;line-height:1.65}.settings-card select:focus,.settings-card textarea:focus,.sentence-editor:focus,.sentence-controls select:focus,.sentence-controls input:focus{border-color:#6990f5;box-shadow:0 0 0 3px #1a4ff01c}.field-help{margin:6px 0 0;color:#8a909c;font-size:9px;line-height:1.5}.field-error{margin:6px 0 0;color:#c34c55;font-size:10px}.voice-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}.split-fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.dictionary-button{width:100%;height:44px;display:flex;align-items:center;justify-content:space-between;padding:0 11px;border:1px solid #d8e0ea;border-radius:10px;color:#575d69;background:#fff}.dictionary-button b{color:var(--blue);font-size:10px}.rate-row strong{color:var(--blue);font-size:11px}.settings-card input[type=range]{width:100%;accent-color:var(--blue)}.range-labels{display:flex;justify-content:space-between;color:#9399a5;font-size:8px}.primary-button,.outline-button,.danger-button{min-height:38px;padding:0 14px;border-radius:10px;font-size:11px;font-weight:700}.primary-button{color:#fff;background:var(--blue);box-shadow:0 5px 12px #1a4ff02b}.outline-button{border:1px solid #bfd0f6;color:var(--blue);background:#fff}.danger-button{color:#fff;background:#cf4651}.compact{height:44px;white-space:nowrap}.primary-button:disabled,.outline-button:disabled,.danger-button:disabled{cursor:not-allowed;opacity:.38;box-shadow:none}.analyze-button{width:100%;height:44px;margin-top:18px}.mini-player{display:grid;grid-template-columns:minmax(80px,1fr) minmax(170px,220px);align-items:center;gap:8px;margin-top:8px;padding:8px 10px;border-radius:10px;background:var(--soft)}.mini-player strong,.mini-player small{display:block}.mini-player strong{font-size:10px}.mini-player small{margin-top:3px;color:#858b97;font-size:8px}.mini-player audio{width:100%;height:32px}.inline-alert{display:grid;grid-template-columns:1fr auto;gap:4px 10px;margin-top:14px;padding:10px;border-radius:10px;font-size:9px}.inline-alert span{grid-column:1}.inline-alert button{grid-column:2;grid-row:1/3;color:inherit;background:none}.inline-alert.error{color:#a74851;background:#fff0f1}.workspace-card{position:relative;min-height:820px;overflow:hidden;padding-bottom:92px;outline:none}.workspace-heading{padding:22px;border-bottom:1px solid var(--line)}.workspace-heading h2 span{display:inline-grid;place-items:center;min-width:24px;height:24px;margin-left:5px;border-radius:999px;color:var(--blue);background:#eef3ff;font-size:10px}.workspace-heading dl{display:flex;gap:22px;margin:0}.workspace-heading dl div{display:grid;justify-items:end}.workspace-heading dt{color:#858b97;font-size:9px}.workspace-heading dd{margin:3px 0 0;font-size:12px;font-weight:800}.empty-state{min-height:540px;display:grid;place-content:center;justify-items:center;padding:30px;text-align:center}.empty-state h3{margin:18px 0 7px;font-size:16px}.empty-state p{max-width:360px;margin:0;color:#7e8490;font-size:11px;line-height:1.6}.empty-state>b{width:46px;height:46px;display:grid;place-items:center;border-radius:14px;color:#c44d57;background:#fff0f1;font-size:22px}.empty-state .outline-button{margin-top:16px}.wave-mark{height:46px;display:flex;align-items:center;gap:3px}.wave-mark i{width:3px;border-radius:999px;background:#79a0fb}.expired-banner{display:flex;align-items:center;gap:10px;margin:14px 18px 0;padding:10px 12px;border-radius:10px;color:#91631d;background:#fff7e7;font-size:10px}.expired-banner span{color:#9c7b45}.batch-toolbar{margin:16px 18px 10px;padding:10px 12px;border-radius:11px;color:#696e79;background:var(--soft);font-size:9px}.batch-toolbar>span,.batch-toolbar>div{display:flex;align-items:center;gap:8px}.batch-toolbar .primary-button,.batch-toolbar .outline-button{min-height:34px}.batch-ok{color:#178663}.batch-fail{color:#c34c55}.sentence-list{display:grid;gap:10px;margin:0;padding:0 18px 18px;list-style:none}.sentence-card{padding:14px;border:1px solid var(--line);border-radius:14px;background:#fff;transition:.18s}.sentence-card.accepted{border-color:#aadcc8;background:#fbfffd}.sentence-card.state-error{border-color:#f0bec2}.sentence-card.state-stale{border-color:#efd294}.sentence-card.state-generating{border-color:#a9c1fa}.sentence-top{justify-content:flex-start}.sentence-index{width:29px;height:29px;display:grid;place-items:center;border-radius:9px;color:var(--blue);background:#edf3ff;font-size:9px;font-weight:800}.status-pill{padding:5px 8px;border-radius:999px;color:#6f7580;background:#f1f3f6;font-size:8px;font-weight:700}.accepted .status-pill{color:#14785a;background:#e8f8f1}.state-error .status-pill{color:#b5444d;background:#fff0f1}.state-stale .status-pill{color:#91631d;background:#fff5df}.version{margin-left:auto;color:#9297a1;font-size:8px}.sentence-text{margin:11px 0;color:#292d36;font-size:12px;line-height:1.65}.sentence-editor{min-height:72px;margin-top:10px;padding:10px;resize:vertical;font-size:11px;line-height:1.6}.chips{display:flex;flex-wrap:wrap;gap:5px}.chips span{padding:4px 7px;border-radius:7px;color:#566276;background:#f0f4fa;font-size:8px}.chips .emphasis{color:#6957bd;background:#f0edff}.sentence-controls{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin-top:9px}.sentence-controls label{color:#727885;font-size:8px}.sentence-controls select,.sentence-controls input{height:34px;margin-top:4px;padding:0 7px}.sentence-player{display:grid;grid-template-columns:1fr auto;align-items:center;gap:10px;margin-top:10px;padding:7px 9px;border-radius:10px;background:var(--soft)}.sentence-player audio{width:100%;height:34px}.sentence-player small{color:#858b97;font-size:8px}.row-error{margin-top:9px;padding:8px 10px;border-radius:8px;color:#aa444d;background:#fff0f1;font-size:9px}.sentence-actions{justify-content:flex-end;margin-top:11px}.sentence-actions .text-action{margin-right:auto}.final-result{align-items:flex-start;margin:0 18px 16px;padding:14px;border:1px solid #bed1fb;border-radius:13px;background:#f6f9ff}.final-result>div strong,.final-result>div small{display:block}.final-result>div small{margin-top:4px;color:#767d89;font-size:9px}.final-result audio{min-width:200px;flex:1;height:36px}.final-result>span{display:flex;align-items:center;gap:7px}.final-result>span small{color:#747b87;font-size:8px}.final-bar{position:absolute;inset:auto 0 0;padding:15px 20px;border-top:1px solid var(--line);background:#fff}.final-bar div strong,.final-bar div span{display:block}.final-bar div strong{font-size:12px}.final-bar div span{margin-top:4px;color:#7b818d;font-size:9px}.assemble-button{min-width:150px;height:44px}.spinner{width:26px;height:26px;display:inline-block;border:3px solid #d7e2fa;border-top-color:var(--blue);border-radius:50%;animation:spin .8s linear infinite}.spinner.small{width:13px;height:13px;border-width:2px}.skeleton{height:720px;background:linear-gradient(90deg,#eef2f6,#f8fafc,#eef2f6);background-size:200% 100%;animation:shimmer 1.2s infinite}.skeleton.large{height:820px}.drawer-layer,.modal-layer{position:fixed;inset:0;z-index:90}.scrim{position:absolute;inset:0;width:100%;background:#08132870}.dictionary-drawer{position:absolute;inset:0 0 0 auto;width:min(520px,100%);display:flex;flex-direction:column;overflow:auto;background:#fff;box-shadow:-20px 0 60px #07152c35;outline:none}.dictionary-drawer>header{display:flex;justify-content:space-between;padding:24px;border-bottom:1px solid var(--line)}.dictionary-drawer h2,.dictionary-drawer h3{margin:0}.dictionary-drawer header p{margin:5px 0 0;color:#818793;font-size:10px}.dictionary-drawer header button{width:34px;height:34px;border-radius:50%;color:#717783;background:#f1f3f6;font-size:20px}.dictionary-toolbar{display:grid;grid-template-columns:1fr auto;gap:8px;padding:16px 24px}.dictionary-toolbar input{height:40px;padding:0 10px}.dictionary-toolbar button,.dictionary-preview button{padding:0 13px;border-radius:9px;color:#fff;background:var(--blue)}.drawer-error{margin:0 24px 10px;padding:9px;color:#a9454e;background:#fff0f1;font-size:10px}.dictionary-loading{display:flex;align-items:center;justify-content:center;gap:10px;padding:36px;color:#747b87;font-size:11px}.dictionary-list{display:grid;gap:8px;max-height:340px;overflow:auto;padding:0 24px}.dictionary-list article{display:grid;grid-template-columns:1fr auto;gap:8px;padding:12px;border:1px solid var(--line);border-radius:11px}.dictionary-list strong,.dictionary-list span,.dictionary-list small{display:block}.dictionary-list strong{font-size:11px}.dictionary-list span{margin-top:4px;color:var(--blue);font-size:10px}.dictionary-list small{margin-top:3px;color:#858b97;font-size:8px}.dictionary-list em{padding:4px 7px;border-radius:6px;background:#eff2f6;font-size:8px;font-style:normal}.dictionary-list article>div:last-child{grid-column:1/-1;display:flex;gap:7px}.dictionary-list article button{padding:5px 8px;border-radius:6px;color:#3b68b5;background:#edf3ff;font-size:8px}.dictionary-list article button.danger{color:#b34851;background:#fff0f1}.dictionary-list article button:disabled{opacity:.35}.dictionary-empty{text-align:center;color:#858b97;font-size:10px}.entry-form,.dictionary-preview{display:grid;gap:9px;margin:15px 24px 0;padding:14px;border-radius:12px;background:var(--soft)}.entry-form h3,.dictionary-preview h3{font-size:13px}.entry-form label{display:grid;gap:4px;color:#666d7a;font-size:9px}.entry-form input{height:36px;padding:0 9px}.entry-form .check{display:flex;align-items:center}.check input{width:auto;height:auto}.entry-form>div{display:flex;justify-content:flex-end;gap:7px}.dictionary-preview>div{display:grid;grid-template-columns:1fr 130px auto;gap:7px}.dictionary-preview input,.dictionary-preview select{height:38px;padding:0 9px}.dictionary-drawer>footer{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:auto;padding:15px 24px;border-top:1px solid var(--line)}.dictionary-drawer>footer span{color:#818793;font-size:8px}.modal-layer{display:grid;place-items:center;padding:20px;background:#08132870}.modal-layer section{width:min(430px,100%);box-sizing:border-box;padding:24px;border-radius:16px;background:#fff;box-shadow:0 24px 70px #07152c45}.modal-layer h2{margin:0;font-size:18px}.modal-layer p{margin:11px 0 20px;color:#6c727e;font-size:11px;line-height:1.7}.modal-layer div{display:flex;justify-content:flex-end;gap:8px}@keyframes spin{to{transform:rotate(360deg)}}@keyframes shimmer{to{background-position:-200% 0}}
.drawer-layer,.modal-layer{--blue:#1a4ff0;--line:#e5ebf2;--soft:#f6faff}
.format-guide{margin-top:10px;padding:10px 11px;border:1px solid #dfe6f0;border-radius:10px;color:#636a77;background:#f8faff;font-size:9px}.format-guide summary{cursor:pointer;color:#3f4a5d;font-weight:700}.format-guide code{display:block;margin-top:9px;padding:8px;border-radius:7px;color:#263d73;background:#eef3ff;white-space:normal}.format-guide div{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}.format-guide div span{padding:4px 6px;border-radius:6px;background:#fff}.format-guide b{color:var(--blue)}.format-guide small{display:block;margin-top:7px;line-height:1.5}.sentence-controls .wide-control{grid-column:1/-1}.sentence-controls .wide-control small{display:block;margin-top:4px;color:#9096a2}
.final-result>div .download-message{max-width:290px;color:#178663;font-weight:700;line-height:1.45}.final-result>div .download-message.error{color:#c34c55}
@media(max-width:1200px) and (min-width:761px){.studio-grid{grid-template-columns:minmax(280px,330px) minmax(470px,1fr);gap:16px}.settings-card{padding:18px}.workspace-heading{padding:18px}.sentence-controls{grid-template-columns:repeat(2,1fr)}.final-result{flex-wrap:wrap}.final-result audio{order:3;width:100%}}
@media(max-width:760px){.studio-intro{margin-top:0}.studio-grid{grid-template-columns:1fr}.workspace-card{min-height:680px}.split-fields,.voice-row,.mini-player{grid-template-columns:1fr}.sentence-controls{grid-template-columns:repeat(2,1fr)}.batch-toolbar{align-items:stretch;flex-direction:column}.batch-toolbar>span{display:grid;grid-template-columns:1fr 1fr}.workspace-heading{align-items:flex-start}.workspace-heading dl{gap:10px}.final-result{align-items:stretch;flex-direction:column}.final-bar{position:sticky;bottom:0;align-items:stretch;flex-direction:column}.assemble-button{width:100%}.dictionary-preview>div{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){.spinner,.skeleton{animation:none}}
.prosody-studio{position:relative}.studio-intro-v3{margin:-14px 0 12px}.studio-intro-v3 h1{font-size:26px;line-height:1.25}.studio-intro-v3 p{margin-top:5px;font-size:12px}.studio-actions{display:flex;align-items:center;gap:10px}.history-button{height:30px;padding:0 11px;border:1px solid #dbe3ed;border-radius:999px;color:#7a8290;background:#fff;font-size:11px}.history-button:disabled{cursor:not-allowed;opacity:.82}.autosave-pill{padding:7px 11px;border-radius:999px;color:#219e57;background:#e8faf0;font-size:11px;font-weight:700}.autosave-pill.unavailable{color:#c74952;background:#ffeded}
.recovery-banner{margin:0 0 12px;padding:9px 12px;border:1px solid #bde6d1;border-radius:10px;color:#14785a;background:#effbf5;font-size:11px}.recovery-banner.error{border-color:#f0bec2;color:#b5444d;background:#fff0f1}
.workflow-stepper{height:48px;box-sizing:border-box;display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:14px;padding:7px;border:1px solid var(--line);border-radius:12px;background:#fff}.workflow-stepper span{display:grid;place-items:center;border-radius:8px;color:var(--muted);background:var(--soft);font-size:11px;font-weight:600}.workflow-stepper span.done{color:#219e57;background:#e8faf0}.workflow-stepper span.active{color:#fff;background:#1459d1}
.studio-grid-v3{grid-template-columns:minmax(300px,330px) minmax(560px,1fr);gap:16px}.studio-grid-v3>.card{border-radius:12px;box-shadow:none}.settings-card-v3{position:relative;min-height:790px;box-sizing:border-box;padding:17px}.settings-card-v3 .card-title{margin-bottom:12px}.settings-card-v3 .card-title h2{font-size:16px}.settings-card-v3 .field-label{margin:11px 0 6px;font-size:11px}.settings-card-v3 select{height:38px}.settings-card-v3 textarea{min-height:150px;font-size:12px}.scene-pill{display:inline-flex;padding:7px 10px;border-radius:999px;color:#666873;background:#f6faff;font-size:11px}.readonly-source{min-height:134px;max-height:158px;overflow:auto;padding:11px;border:1px solid var(--line);border-radius:10px;white-space:pre-wrap;color:#242833;background:var(--soft);font-size:12px;line-height:1.55}.section-divider{height:1px;margin:16px 0;background:var(--line)}.settings-heading{margin:0 0 12px;font-size:14px}.voice-select-button{width:100%;height:58px;display:flex;align-items:center;justify-content:space-between;padding:8px 11px;border:1px solid var(--line);border-radius:10px;text-align:left;color:var(--ink);background:#fff}.voice-select-button span,.voice-select-button strong,.voice-select-button small{display:block}.voice-select-button strong{font-size:13px}.voice-select-button strong em{color:#0a85ff;font-style:normal}.voice-select-button small{margin-top:5px;color:var(--muted);font-size:10px}.voice-select-button>b{color:#0a85ff;font-size:11px}.voice-library-note{margin:5px 0 10px;color:#616e80;font-size:10px}.quick-settings{display:flex;gap:6px;margin-top:8px}.quick-settings label{min-width:0}.quick-settings select{height:30px;padding:0 9px;border-radius:8px;font-size:10px}.quick-settings.secondary{position:relative;align-items:flex-start}.dictionary-status{height:29px;padding:0 10px;border-radius:999px;color:#219e57;background:#e8faf0;font-size:10px;font-weight:700}.advanced-settings{position:relative}.advanced-settings summary{height:29px;box-sizing:border-box;padding:7px 10px;border:1px solid var(--line);border-radius:8px;color:var(--muted);background:#fff;font-size:10px;list-style:none;cursor:pointer}.advanced-settings[open]{position:absolute;z-index:9;left:0;top:0;width:270px;padding:10px;border:1px solid var(--line);border-radius:10px;background:#fff;box-shadow:0 12px 30px #0a1a3825}.advanced-settings[open] summary{margin-bottom:10px}.advanced-settings input[type=range]{width:100%}.advanced-settings .dictionary-button{margin-top:8px}.safety-tip{display:grid;gap:5px;margin-top:12px;padding:10px 11px;border-radius:10px;color:var(--ink);background:#ebf5ff;font-size:10px}.safety-tip strong{color:#0a85ff}.production-standard{display:grid;gap:5px;margin-top:8px;padding:10px 11px;border:1px solid #e0e5f0;border-radius:12px;background:#f5f7fc;font-size:10px}.production-standard strong{font-size:13px}.production-standard b{color:#1459d1}.production-standard span{color:#616e80;line-height:1.45}.production-standard small{color:#616e80}.restructure-button{width:100%;margin-top:10px}.structure-note{margin:5px 0 0;text-align:center;color:var(--muted);font-size:9px}
.voice-selector{position:absolute;z-index:30;left:calc(100% + 12px);top:230px;width:340px;box-sizing:border-box;display:grid;gap:10px;padding:16px;border:1px solid #dbe3ed;border-radius:16px;background:#fff;box-shadow:0 10px 28px #0a1a3824}.voice-selector>header{display:flex;align-items:center;justify-content:space-between}.voice-selector>header strong{font-size:16px}.voice-selector>header button{color:#0a85ff;background:transparent;font-size:11px}.voice-selector>input{height:36px;padding:0 12px;border:1px solid #dbe3ed;border-radius:10px;color:#1f242e;background:#fbfcff;outline:none}.voice-tabs{display:flex;flex-wrap:wrap;gap:6px}.voice-tabs button{padding:7px 11px;border:1px solid #dbe3ed;border-radius:999px;color:#666e7d;background:#fff;font-size:11px}.voice-tabs button.active{border-color:#0a85ff;color:#fff;background:#0a85ff}.selector-label,.voice-local-note{color:#666e7d;font-size:10px}.voice-options{display:grid;gap:8px;max-height:250px;overflow:auto}.voice-options article{height:64px;display:grid;grid-template-columns:minmax(0,1fr) auto auto auto;align-items:center;gap:9px;padding:0 11px;border:1px solid #dbe3ed;border-radius:12px}.voice-options article.selected{border-color:#0a85ff;background:#ebf5ff}.voice-option-main{min-width:0;text-align:left;background:transparent}.voice-option-main strong,.voice-option-main small{display:block}.voice-option-main strong{color:#1f242e;font-size:12px}.voice-option-main small{margin-top:5px;overflow:hidden;text-overflow:ellipsis;color:#666e7d;font-size:10px;white-space:nowrap}.voice-preview,.favorite-button{color:#0a85ff;background:transparent;font-size:10px;white-space:nowrap}.favorite-button{font-size:18px}.voice-check{color:#0a85ff;font-weight:800}.voice-empty{margin:15px 0;text-align:center;color:#7b8290;font-size:11px}.voice-local-note{line-height:1.45}
.workspace-card-v3{height:790px;min-height:790px;box-sizing:border-box;padding-bottom:72px}.workspace-card-v3 .workspace-heading{padding:17px 16px 5px;border-bottom:0}.workspace-card-v3 .workspace-heading h2{font-size:18px}.status-summary{display:flex;gap:6px;padding:7px 16px}.status-summary span{padding:6px 10px;border-radius:999px;color:var(--muted);background:var(--soft);font-size:10px}.status-summary .confirmed{color:#219e57;background:#e8faf0}.status-summary .failed{color:#d12e2e;background:#ffeded}.workspace-tools{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:3px 16px 10px}.sentence-filters,.batch-actions{display:flex;align-items:center;gap:6px}.sentence-filters button{padding:6px 9px;border-radius:999px;color:var(--muted);background:var(--soft);font-size:9px}.sentence-filters button.active{color:#fff;background:#0a85ff}.batch-actions{margin-left:auto}.batch-actions>span{color:var(--muted);font-size:9px}.batch-actions .outline-button,.batch-actions .primary-button{min-height:32px;padding:0 10px}.batch-result b{color:#d12e2e}.workspace-card-v3 .sentence-list{max-height:562px;overflow:auto;gap:8px;padding:0 12px 12px}.workspace-card-v3 .sentence-card{position:relative;min-height:148px;box-sizing:border-box;padding:12px 14px 11px;border-color:var(--line);overflow:hidden}.workspace-card-v3 .sentence-card:before{content:"";position:absolute;inset:-1px auto -1px -1px;width:4px;background:#0a85ff}.workspace-card-v3 .sentence-card.accepted:before{background:#219e57}.workspace-card-v3 .sentence-card.state-error:before{background:#d12e2e}.workspace-card-v3 .sentence-card.state-stale:before{background:#d17a0d}.workspace-card-v3 .sentence-card.accepted{border-color:var(--line);background:#fff}.workspace-card-v3 .sentence-top{height:24px}.workspace-card-v3 .sentence-index{width:auto;height:auto;border-radius:0;color:var(--ink);background:transparent;font-size:11px}.workspace-card-v3 .status-pill{padding:5px 9px;font-size:10px}.workspace-card-v3 .version{margin-left:0;font-size:9px}.sentence-settings{margin-left:auto;color:var(--muted);background:transparent;font-size:9px}.workspace-card-v3 .sentence-text{margin:9px 0 7px;font-size:12px;font-weight:600;line-height:1.45}.workspace-card-v3 .sentence-player{grid-template-columns:minmax(180px,1fr) auto;max-width:58%;margin:0;padding:0;background:#fff}.workspace-card-v3 .sentence-player audio{height:32px}.audio-placeholder{display:flex;align-items:center;gap:10px;height:32px;color:#0a85ff}.audio-placeholder small{color:var(--muted);font-size:9px}.workspace-card-v3 .sentence-actions{min-height:36px;margin-top:4px}.workspace-card-v3 .sentence-actions button{min-height:32px}.state-note{margin-right:auto;color:var(--muted);font-size:9px}.state-note.error{color:#d12e2e}.state-note.edited{color:#d17a0d}.filtered-empty{padding:80px 20px;text-align:center;color:var(--muted);font-size:12px;list-style:none}.hidden-note{margin:0 16px;color:var(--muted);font-size:9px}.workspace-card-v3 .final-bar{padding:11px 14px}.workspace-card-v3 .final-bar div{margin-right:auto}.sequence-button{min-width:110px}.workspace-card-v3 .assemble-button{min-width:140px;height:38px}.workspace-card-v3 .empty-state{min-height:570px}.sr-only{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:1180px) and (min-width:761px){.studio-grid-v3{grid-template-columns:minmax(280px,310px) minmax(480px,1fr)}.sentence-filters button{padding:6px}.workspace-tools{align-items:flex-start;flex-direction:column}.batch-actions{margin-left:0}.workspace-card-v3 .sentence-list{max-height:520px}.voice-selector{left:12px;right:12px;top:250px;width:auto}}
@media(max-width:760px){.studio-intro-v3{align-items:flex-start}.studio-actions{align-items:flex-end;flex-direction:column}.history-button{display:none}.workflow-stepper{grid-template-columns:repeat(4,minmax(74px,1fr));gap:5px;overflow:auto}.studio-grid-v3{grid-template-columns:1fr}.settings-card-v3{min-height:auto}.voice-selector{position:fixed;inset:10vh 16px auto;width:auto;max-height:80vh;overflow:auto}.workspace-card-v3{height:auto;min-height:680px}.workspace-tools{align-items:stretch;flex-direction:column}.sentence-filters,.batch-actions{overflow:auto}.batch-actions{margin-left:0}.workspace-card-v3 .sentence-list{max-height:none}.workspace-card-v3 .sentence-player{max-width:100%}.workspace-card-v3 .final-bar{position:sticky;flex-direction:row;flex-wrap:wrap}.workspace-card-v3 .final-bar div{width:100%}.sequence-button,.workspace-card-v3 .assemble-button{flex:1}.quick-settings{flex-wrap:wrap}}
</style>
