const select = document.querySelector("#wordSelect");
const recordButton = document.querySelector("#recordButton");
const recordLabel = document.querySelector("#recordLabel");
const listenButton = document.querySelector("#listenButton");
const statusText = document.querySelector("#statusText");
const resultCard = document.querySelector("#resultCard");

let words = [];
let recorder = null;
let chunks = [];

function selectedWord() {
  return words.find((word) => word.id === select.value) || words[0];
}

function renderWord() {
  const word = selectedWord();
  if (!word) return;
  document.querySelector("#wordText").textContent = word.word;
  document.querySelector("#wordIpa").textContent = word.ipa;
  document.querySelector("#wordMeaning").textContent = word.translation;
  document.querySelector("#focusText").textContent = `重点音 ${word.focus_phones.map((phone) => `/${phone}/`).join(" · ")}`;
  resultCard.classList.add("hidden");
}

async function loadWords() {
  const response = await fetch("/api/v1/words");
  words = await response.json();
  select.innerHTML = words.map((word) => `<option value="${word.id}">${word.word} · ${word.translation}</option>`).join("");
  renderWord();
}

listenButton.addEventListener("click", () => {
  const word = selectedWord();
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(word.word);
  utterance.lang = "en-US";
  utterance.rate = 0.78;
  speechSynthesis.speak(utterance);
});

select.addEventListener("change", renderWord);

recordButton.addEventListener("click", async () => {
  if (recorder?.state === "recording") {
    recorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg"].find((type) => MediaRecorder.isTypeSupported(type));
    recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    chunks = [];
    recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
    recorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      recordButton.classList.remove("recording");
      recordButton.disabled = true;
      recordLabel.textContent = "正在分析…";
      statusText.textContent = "正在定位重点音素";
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      await submitRecording(blob);
      recordButton.disabled = false;
      recordLabel.textContent = "重新录音";
    };
    recorder.start();
    recordButton.classList.add("recording");
    recordLabel.textContent = "结束录音";
    statusText.textContent = "录音中…完整读出一个单词";
    setTimeout(() => { if (recorder?.state === "recording") recorder.stop(); }, 5000);
  } catch (error) {
    statusText.textContent = "无法使用麦克风，请检查浏览器权限。";
  }
});

async function submitRecording(blob) {
  const form = new FormData();
  form.append("word_id", selectedWord().id);
  form.append("audio", blob, "recording.webm");
  try {
    const response = await fetch("/api/v1/assess", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "评分失败");
    renderResult(payload);
    statusText.textContent = "分析完成，可以再次录音。";
  } catch (error) {
    statusText.textContent = error.message;
  }
}

function renderResult(result) {
  const titles = { excellent: "发音清晰", good: "接近标准", needs_practice: "继续练习" };
  document.querySelector("#resultTitle").textContent = titles[result.verdict];
  document.querySelector("#scoreValue").textContent = result.score;
  document.querySelector("#expectedPhones").textContent = `/${result.expected_phones.join(" ")}/`;
  document.querySelector("#heardPhones").textContent = result.heard_phones.length ? `/${result.heard_phones.join(" ")}/` : "未识别";
  const feedback = result.feedback[0];
  document.querySelector("#feedback").innerHTML = `<h3>${feedback.title}</h3><p>${feedback.message}</p><p>${feedback.tip}</p>`;
  document.querySelector("#metrics").textContent = `录音 ${result.metrics.audio_seconds}s · 推理 ${result.metrics.inference_ms}ms`;
  resultCard.classList.remove("hidden");
}

loadWords().catch(() => { statusText.textContent = "词库加载失败，请检查服务状态。"; });

