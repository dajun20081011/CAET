<template>
  <main class="cl-login">
    <!-- 左侧品牌视觉 -->
    <section class="cl-hero" aria-label="CabinLingo 品牌区">
      <div class="flight-path" aria-hidden="true">
        <span class="flight-line"></span>
        <span class="flight-plane">✈</span>
      </div>

      <div class="hero-content">
        <div class="hero-logo">
          <img src="/cabinlingo-mark.svg" alt="" />
          <div class="hero-wordmark">
            <span class="word-cabin">Cabin</span><span class="word-lingo">Lingo</span>
          </div>
        </div>

        <div class="hero-tagline">
          <span>LISTEN</span><i></i><span>SPEAK</span><i class="green"></i><span>GROW</span>
        </div>

        <h1>让每一次开口，都更接近专业表达</h1>

        <div class="hero-categories">
          <span>客舱英语</span><i></i>
          <span>广播词</span><i class="green"></i>
          <span>情景训练</span>
        </div>
      </div>

      <div class="sound-waves" aria-hidden="true">
        <span class="wave-line wave-a"></span>
        <span class="wave-line wave-b"></span>
        <span class="wave-line wave-c"></span>
        <span class="wave-line wave-d"></span>
      </div>

      <div class="dot-grid" aria-hidden="true">
        <i v-for="n in 24" :key="n"></i>
      </div>
    </section>

    <!-- 右侧登录 -->
    <section class="cl-panel">
      <div class="cl-card">
        <div class="card-brand">
          <BrandMark />
        </div>

        <div class="card-heading">
          <h2>欢迎回来</h2>
          <p>登录 CabinLingo，继续今天的学习</p>
        </div>

        <form aria-label="CabinLingo 登录" @submit.prevent="submit">
          <label class="cl-field">
            <span class="field-icon" aria-hidden="true">
              <AppIcon name="user" />
            </span>
            <input
              v-model="account"
              placeholder="请输入账号/工号"
              autocomplete="username"
              inputmode="text"
              required
            />
          </label>

          <label class="cl-field">
            <span class="field-icon" aria-hidden="true">
              <AppIcon name="lock" />
            </span>
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              placeholder="请输入密码"
              autocomplete="current-password"
              required
            />
            <button
              type="button"
              class="field-action"
              :aria-label="showPassword ? '隐藏密码' : '显示密码'"
              @click="showPassword = !showPassword"
            >
              <AppIcon name="view" />
            </button>
          </label>

          <div class="cl-options">
            <label>
              <input v-model="remember" type="checkbox" />
              <span>保持登录</span>
            </label>

            <button
              type="button"
              class="forgot"
              @click="forgotMessage = '请联系本单位 CabinLingo 管理员重置密码。'"
            >
              忘记密码？
            </button>
          </div>

          <p v-if="forgotMessage" class="cl-hint" role="status">
            {{ forgotMessage }}
          </p>

          <p v-if="error" class="cl-error" role="alert">
            {{ error }}
          </p>

          <button
            class="login-button"
            :disabled="loading || !account || !password"
          >
            {{ loading ? '登录中…' : '登 录' }}
          </button>
        </form>

        <p class="agreement">
          登录即表示您已阅读并同意
          <span>用户协议</span>
          <b>·</b>
          <span>隐私政策</span>
        </p>
      </div>
    </section>
  </main>
  <!-- CABINLINGO_ICP_START -->
  <footer class="icp-footer" aria-label="网站备案信息">
    <a
      href="https://beian.miit.gov.cn/"
      target="_blank"
      rel="noopener noreferrer"
    >
      皖ICP备2026024661号
    </a>
  </footer>
  <!-- CABINLINGO_ICP_END -->
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import BrandMark from '@/components/BrandMark.vue'
import { useSessionStore } from '@/stores/session'
import { authErrorMessage } from '@/api'

const router = useRouter()
const route = useRoute()
const session = useSessionStore()
const account = ref('')
const password = ref('')
const remember = ref(true)
const showPassword = ref(false)
const loading = ref(false)
const error = ref('')
const forgotMessage = ref('')

watch(() => route.query.reason, (reason) => {
  if (reason === 'expired') error.value = '登录已失效，请重新登录。'
}, { immediate: true })

async function submit() {
  if (!account.value || !password.value) {
    error.value = '请输入账号和密码'
    return
  }

  loading.value = true
  error.value = ''
  forgotMessage.value = ''

  try {
    await session.signIn(account.value.trim(), password.value, remember.value)
    await router.replace(session.landingPage())
  } catch (cause) {
    error.value = authErrorMessage(cause, true)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.cl-login {
  --brand-blue: #1264f4;
  --deep-blue: #082b78;
  --cyan: #60b7ff;
  --green: #22c3a7;
  min-height: 100vh;
  display: grid;
  grid-template-columns: 54% 46%;
  overflow: hidden;
  background:
    radial-gradient(circle at 18% 18%, rgba(96,183,255,.24), transparent 35%),
    linear-gradient(125deg,#eaf4ff 0%,#f5f9ff 48%,#edf5ff 100%);
}

/* LEFT */

.cl-hero {
  min-height: 100vh;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.cl-hero::before {
  content: "";
  position: absolute;
  width: 620px;
  height: 620px;
  left: 6%;
  top: 10%;
  border-radius: 50%;
  background: radial-gradient(circle,rgba(89,166,255,.16),transparent 68%);
  filter: blur(10px);
}

.hero-content {
  position: relative;
  z-index: 4;
  width: min(680px,78%);
  text-align: center;
  transform: translateY(-3%);
}

.hero-logo {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.hero-logo img {
  width: 220px;
  height: 160px;
  object-fit: contain;
  filter: drop-shadow(0 16px 30px rgba(26,103,222,.14));
}

.hero-wordmark {
  margin-top: 4px;
  font-family: Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size: clamp(64px,5.2vw,94px);
  line-height: .98;
  font-weight: 760;
  letter-spacing: -5px;
}

.word-cabin {
  color: #082c79;
}

.word-lingo {
  color: #1264f4;
}

.hero-tagline {
  margin-top: 34px;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 23px;
  color: #405f96;
  font-size: 19px;
  font-weight: 600;
  letter-spacing: 8px;
}

.hero-tagline i,
.hero-categories i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-blue);
  flex: 0 0 auto;
}

.hero-tagline i.green,
.hero-categories i.green {
  background: var(--green);
}

.hero-content h1 {
  margin: 38px 0 0;
  color: #0a367e;
  font-size: clamp(26px,2vw,36px);
  font-weight: 720;
  letter-spacing: 1px;
}

.hero-categories {
  margin-top: 25px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 17px;
  color: #617ba7;
  font-size: 17px;
  letter-spacing: 3px;
}

/* PLANE */

.flight-path {
  position: absolute;
  left: -20px;
  top: 8%;
  width: 300px;
  height: 140px;
  z-index: 2;
  opacity: .7;
}

.flight-line {
  position: absolute;
  left: -25px;
  top: 65px;
  width: 245px;
  height: 75px;
  border-top: 2px dashed rgba(48,128,239,.42);
  border-radius: 50%;
  transform: rotate(-7deg);
}

.flight-plane {
  position: absolute;
  left: 205px;
  top: 19px;
  color: #4c9af5;
  font-size: 43px;
  transform: rotate(-18deg);
}

/* WAVES */

.sound-waves {
  position: absolute;
  z-index: 1;
  left: -8%;
  right: -10%;
  bottom: -30px;
  height: 260px;
  opacity: .76;
}

.wave-line {
  position: absolute;
  left: -10%;
  width: 120%;
  height: 180px;
  border-radius: 50%;
}

.wave-a {
  bottom: -55px;
  background: linear-gradient(100deg,rgba(38,99,235,.27),rgba(96,183,255,.17),rgba(34,195,167,.12));
  transform: rotate(6deg);
}

.wave-b {
  bottom: -90px;
  background: linear-gradient(100deg,rgba(27,109,246,.34),rgba(125,211,252,.18),transparent 75%);
  transform: rotate(-7deg);
}

.wave-c {
  bottom: -112px;
  border-top: 1px solid rgba(52,137,246,.34);
  box-shadow:
    0 -7px 0 rgba(52,137,246,.08),
    0 -14px 0 rgba(52,137,246,.06),
    0 -21px 0 rgba(34,195,167,.05);
  transform: rotate(4deg);
}

.wave-d {
  bottom: -125px;
  border-top: 1px solid rgba(34,195,167,.30);
  transform: rotate(-9deg);
}

.dot-grid {
  position: absolute;
  left: 42px;
  bottom: 34px;
  z-index: 3;
  width: 90px;
  display: grid;
  grid-template-columns: repeat(6,6px);
  gap: 9px;
  opacity: .48;
}

.dot-grid i {
  width: 6px;
  height: 6px;
  background: #66aaf7;
  border-radius: 50%;
}

/* RIGHT */

.cl-panel {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 54px 7vw 54px 3vw;
}

.cl-card {
  position: relative;
  width: min(600px,100%);
  padding: 60px 58px 50px;
  border: 1px solid rgba(255,255,255,.8);
  border-radius: 34px;
  background: rgba(255,255,255,.93);
  box-shadow:
    0 30px 80px rgba(32,76,139,.14),
    inset 0 1px 0 rgba(255,255,255,.9);
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
}

.card-brand {
  display: flex;
  justify-content: center;
  margin-bottom: 45px;
}

.card-brand :deep(.brand-mark__icon) {
  width: 48px;
  height: 36px;
}

.card-brand :deep(.brand-mark__name) {
  font-size: 29px;
}

.card-heading {
  text-align: center;
}

.card-heading h2 {
  margin: 0;
  color: #092b64;
  font-size: 38px;
  line-height: 1.2;
  font-weight: 760;
  letter-spacing: 1px;
}

.card-heading p {
  margin: 15px 0 38px;
  color: #8193b4;
  font-size: 17px;
}

.cl-field {
  height: 72px;
  display: flex;
  align-items: center;
  margin: 18px 0;
  padding: 0 23px;
  border: 1px solid #d7e1ef;
  border-radius: 16px;
  background: rgba(255,255,255,.76);
  box-shadow: 0 6px 18px rgba(33,80,145,.035);
  transition: .2s ease;
}

.cl-field:focus-within {
  border-color: #75aaf7;
  box-shadow: 0 0 0 4px rgba(38,116,240,.08);
}

.field-icon {
  display: flex;
  margin-right: 17px;
  color: #7288ac;
  font-size: 26px;
}

.cl-field input {
  flex: 1;
  width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: #17365f;
  font-size: 17px;
}

.cl-field input::placeholder {
  color: #9aaac3;
}

.field-action {
  display: flex;
  border: 0;
  padding: 8px;
  color: #7087ac;
  background: transparent;
  cursor: pointer;
  font-size: 22px;
}

.cl-options {
  margin: 23px 2px 30px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #657b9f;
  font-size: 15px;
}

.cl-options label {
  display: flex;
  align-items: center;
  gap: 9px;
}

.cl-options input {
  width: 18px;
  height: 18px;
  accent-color: var(--brand-blue);
}

.forgot {
  border: 0;
  background: transparent;
  color: #0865ef;
  cursor: pointer;
  font-size: 15px;
}

.login-button {
  width: 100%;
  height: 68px;
  border: 0;
  border-radius: 16px;
  color: #fff;
  background: linear-gradient(100deg,#0960ed 0%,#0875fa 55%,#278bf7 100%);
  box-shadow: 0 15px 32px rgba(20,104,236,.26);
  cursor: pointer;
  font-size: 21px;
  font-weight: 650;
  letter-spacing: 7px;
  transition: transform .2s ease,box-shadow .2s ease;
}

.login-button:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 18px 36px rgba(20,104,236,.32);
}

.login-button:disabled {
  opacity: .62;
  cursor: default;
}

.agreement {
  margin: 34px 0 0;
  text-align: center;
  color: #8b9bb5;
  font-size: 13px;
}

.agreement span {
  color: #0968ef;
}

.agreement b {
  margin: 0 6px;
  font-weight: 400;
}

.cl-error,
.cl-hint {
  margin: -10px 0 17px;
  padding: 10px 13px;
  border-radius: 10px;
  font-size: 13px;
}

.cl-error {
  color: #d9485f;
  background: #fff1f3;
}

.cl-hint {
  color: #496b9b;
  background: #f1f6fd;
}

/* iPad portrait / smaller tablets */

@media (max-width: 1024px) {
  .cl-login {
    grid-template-columns: 46% 54%;
  }

  .hero-content {
    width: 88%;
  }

  .hero-logo img {
    width: 155px;
    height: 115px;
  }

  .hero-wordmark {
    font-size: 54px;
    letter-spacing: -3px;
  }

  .hero-tagline {
    gap: 12px;
    font-size: 13px;
    letter-spacing: 4px;
  }

  .hero-content h1 {
    font-size: 24px;
  }

  .hero-categories {
    font-size: 14px;
    letter-spacing: 1px;
  }

  .cl-panel {
    padding: 35px 30px;
  }

  .cl-card {
    padding: 48px 38px 40px;
  }
}

/* iPad portrait / mobile */

@media (max-width: 820px) {
  .cl-login {
    display: block;
    min-height: 100svh;
    overflow: auto;
    padding: 0;
    background:
      radial-gradient(circle at 50% 0%,rgba(74,158,255,.26),transparent 37%),
      linear-gradient(180deg,#e5f2ff 0%,#f6faff 48%,#eef6ff 100%);
  }

  .cl-hero {
    min-height: auto;
    height: 265px;
    display: block;
    padding-top: 30px;
  }

  .hero-content {
    width: 100%;
    transform: none;
  }

  .hero-logo img {
    width: 94px;
    height: 68px;
  }

  .hero-wordmark {
    margin-top: -2px;
    font-size: 42px;
    letter-spacing: -2.5px;
  }

  .hero-tagline {
    margin-top: 15px;
    font-size: 10px;
    gap: 10px;
    letter-spacing: 3px;
  }

  .hero-content h1 {
    margin-top: 17px;
    font-size: 17px;
  }

  .hero-categories {
    display: none;
  }

  .flight-path {
    opacity: .35;
    transform: scale(.7);
    transform-origin: left top;
  }

  .sound-waves {
    height: 120px;
    bottom: -30px;
  }

  .dot-grid {
    display: none;
  }

  .cl-panel {
    min-height: auto;
    display: block;
    padding: 0 18px 28px;
  }

  .cl-card {
    width: min(520px,100%);
    margin: 0 auto;
    padding: 31px 25px 28px;
    border-radius: 27px;
  }

  .card-brand {
    display: none;
  }

  .card-heading h2 {
    font-size: 28px;
  }

  .card-heading p {
    margin: 10px 0 24px;
    font-size: 14px;
  }

  .cl-field {
    height: 58px;
    margin: 13px 0;
    padding: 0 17px;
  }

  .cl-options {
    margin: 17px 2px 22px;
    font-size: 13px;
  }

  .forgot {
    font-size: 13px;
  }

  .login-button {
    height: 58px;
    font-size: 18px;
  }

  .agreement {
    margin-top: 23px;
    font-size: 11px;
  }
}

@media (max-width: 420px) {
  .cl-hero {
    height: 235px;
  }

  .hero-logo img {
    width: 80px;
    height: 58px;
  }

  .hero-wordmark {
    font-size: 37px;
  }

  .hero-content h1 {
    font-size: 15px;
  }

  .cl-card {
    padding: 27px 20px 24px;
  }
}

/* CABINLINGO_ICP_STYLE */
.icp-footer {
  width: 100%;
  box-sizing: border-box;
  margin-top: 20px;
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom));
  text-align: center;
  font-size: 12px;
  line-height: 1.5;
}
.icp-footer a {
  color: rgba(100, 116, 139, 0.72);
  text-decoration: none;
  transition: color 0.2s ease;
}
.icp-footer a:hover {
  color: rgba(71, 85, 105, 0.95);
  text-decoration: underline;
}
</style>
