interface CabinSpeechRecognitionAlternative {
  readonly transcript: string
  readonly confidence: number
}

interface CabinSpeechRecognitionResult {
  readonly isFinal: boolean
  readonly length: number
  readonly [index: number]: CabinSpeechRecognitionAlternative
}

interface CabinSpeechRecognitionEvent extends Event {
  readonly resultIndex: number
  readonly results: {
    readonly length: number
    readonly [index: number]: CabinSpeechRecognitionResult
  }
}

interface CabinSpeechRecognitionErrorEvent extends Event {
  readonly error: string
  readonly message: string
}

interface CabinSpeechRecognition {
  continuous: boolean
  interimResults: boolean
  lang: string
  maxAlternatives: number
  onresult: ((event: CabinSpeechRecognitionEvent) => void) | null
  onerror: ((event: CabinSpeechRecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}

interface CabinSpeechRecognitionConstructor {
  new (): CabinSpeechRecognition
}

interface Window {
  SpeechRecognition?: CabinSpeechRecognitionConstructor
  webkitSpeechRecognition?: CabinSpeechRecognitionConstructor
}
