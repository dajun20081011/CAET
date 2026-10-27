import axios from 'axios'
import { readAccessToken } from '@/api'

const pronunciationHttp = axios.create({
  baseURL: '/pronunciation-api/api/v1',
  timeout: 35000,
})

pronunciationHttp.interceptors.request.use((config) => {
  const token = readAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export interface PronunciationWord {
  id: string
  word: string
  translation: string
  category: string
  ipa: string
  focus_phones: string[]
}

export interface PronunciationFeedback {
  type: string
  title: string
  message: string
  tip: string
}

export interface PronunciationPhoneme {
  status: 'correct' | 'substitution' | 'deletion' | 'insertion'
  expected_index: number | null
  expected: string | null
  heard: string | null
  confidence: number | null
  severity: 'none' | 'minor' | 'major' | 'target'
  tip?: string
}

export interface PronunciationAssessment {
  request_id: string
  word: PronunciationWord
  score: number
  verdict: 'excellent' | 'good' | 'needs_practice'
  expected_phones: string[]
  heard_phones: string[]
  heard_phone_confidence: number[]
  phonemes: PronunciationPhoneme[]
  feedback: PronunciationFeedback[]
  metrics: {
    audio_seconds: number
    inference_ms: number
    target_error_count: number
  }
  model: string
}

export const pronunciationApi = {
  async words(): Promise<PronunciationWord[]> {
    const { data } = await pronunciationHttp.get<PronunciationWord[]>('/words')
    return data
  },

  async resolveWords(words: string[]): Promise<PronunciationWord[]> {
    const { data } = await pronunciationHttp.post<PronunciationWord[]>('/words/resolve', { words })
    return data
  },

  async assess(wordId: string, audio: Blob): Promise<PronunciationAssessment> {
    const body = new FormData()
    body.append('word_id', wordId)
    const extension = audio.type.includes('mp4') ? 'm4a' : audio.type.includes('ogg') ? 'ogg' : 'webm'
    body.append('audio', audio, `pronunciation.${extension}`)
    const { data } = await pronunciationHttp.post<PronunciationAssessment>('/assess', body)
    return data
  },
}
