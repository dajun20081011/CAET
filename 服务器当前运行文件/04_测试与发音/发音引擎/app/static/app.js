const $ = (id) => document.getElementById(id);
let words = [];
let audioBlob = null;
let stream = null;
let context = null;
let processor = null;
let chunks = [];

function headers() {
  const key = $('apiKey').value.trim();
  return key ? {'X-API-Key': key} : {};
}

function setStatus(text, isError = false) {
  $('status').textContent = text;
  $('status').style.color = isError ? 'var(--red)' : '';
}

function selectedWord() { return words.find((item) => item.id === $('word').value); }

function showWord() {
  const item = selectedWord();
  if (!item) return;
  $('wordMeta').innerHTML = `<strong>${item.display}</strong> ${item.ipa} · ${item.meaning_zh}<br>${item.coaching_tip_zh}`;
  $('result').hidden = true;
}

function encodeWav(channelData, sampleRate) {
  const length = channelData.reduce((sum, chunk) => sum + chunk.length, 0);
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const write = (offset, text) => [...text].forEach((char, i) => view.setUint8(offset + i, char.charCodeAt(0)));
  write(0, 'RIFF'); view.setUint32(4, 36 + length * 2, true); write(8, 'WAVE'); write(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); write(36, 'data'); view.setUint32(40, length * 2, true);
  let offset = 44;
  for (const chunk of channelData) for (const sample of chunk) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 32768 : clamped * 32767, true); offset += 2;
  }
  return new Blob([view], {type: 'audio/wav'});
}

async function startRecording() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: false, noiseSuppression: false}});
    context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    processor = context.createScriptProcessor(4096, 1, 1);
    chunks = [];
    processor.onaudioprocess = (event) => chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
    source.connect(processor); processor.connect(context.destination);
    $('record').disabled = true; $('stop').disabled = false; $('submit').disabled = true;
    setStatus('录音中…请清楚读出所选单词。');
  } catch (error) { setStatus(`无法使用麦克风：${error.message}`, true); }
}

async function stopRecording() {
  processor.disconnect(); stream.getTracks().forEach((track) => track.stop());
  audioBlob = encodeWav(chunks, context.sampleRate); await context.close();
  $('preview').src = URL.createObjectURL(audioBlob); $('preview').hidden = false;
  $('record').disabled = false; $('stop').disabled = true; $('submit').disabled = false;
  setStatus('录音完成，可以开始分析。');
}

function renderResult(data) {
  $('score').textContent = data.overall_score.toFixed(1);
  $('errorCount').textContent = `${data.error_count} 个`;
  $('latency').textContent = `${data.latency_ms} ms`;
  const labels = {correct:'正确', weak:'偏弱', substitution:'替换', deletion:'漏读'};
  $('phones').innerHTML = data.words.flatMap((word) => word.phonemes).map((phone) => `
    <article class="phone ${phone.diagnosis}">
      <div class="phone-symbol">/${phone.expected_ipa}/</div>
      <div><strong>${phone.score.toFixed(1)} 分${phone.observed ? ` · 检测 /${phone.observed}/` : ''}</strong><p>${phone.feedback_zh}</p></div>
      <span class="badge">${labels[phone.diagnosis]}</span>
    </article>`).join('');
  $('raw').textContent = JSON.stringify(data, null, 2);
  $('result').hidden = false;
  $('result').scrollIntoView({behavior:'smooth', block:'start'});
}

async function submit() {
  if (!audioBlob) return;
  $('submit').disabled = true; setStatus('正在分析；首次运行可能需要加载模型…');
  const form = new FormData(); form.append('word_id', $('word').value); form.append('audio', audioBlob, 'recording.wav');
  try {
    const response = await fetch('/api/v1/assess', {method:'POST', headers:headers(), body:form});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.error?.message || `HTTP ${response.status}`);
    renderResult(data); setStatus('分析完成。');
  } catch (error) { setStatus(`分析失败：${error.message}`, true); }
  finally { $('submit').disabled = false; }
}

$('record').addEventListener('click', startRecording);
$('stop').addEventListener('click', stopRecording);
$('submit').addEventListener('click', submit);
$('word').addEventListener('change', showWord);
$('file').addEventListener('change', (event) => {
  const file = event.target.files[0]; if (!file) return;
  audioBlob = file; $('preview').src = URL.createObjectURL(file); $('preview').hidden = false;
  $('submit').disabled = false; setStatus(`已选择：${file.name}`);
});

async function loadWords() {
  try {
    const response = await fetch('/api/v1/words', {headers:headers()});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    words = await response.json(); $('word').innerHTML = words.map((item) => `<option value="${item.id}">${item.display} · ${item.meaning_zh}</option>`).join('');
    showWord(); setStatus(`已加载 ${words.length} 个航空英语词。`);
  } catch (error) { setStatus(`词库加载失败：${error.message}。如启用了 API Key，请填写后离开输入框。`, true); }
}

$('apiKey').addEventListener('change', loadWords);
loadWords();
