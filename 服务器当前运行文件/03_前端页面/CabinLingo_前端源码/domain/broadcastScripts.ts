export const BROADCAST_SCRIPT_TYPE_OPTIONS = [
  { value: '常用广播', label: '常用广播' },
  { value: '通用广播', label: '通用广播' },
  { value: '应急广播', label: '应急广播' },
  { value: '机场地名', label: '机场地名' },
] as const

export type BroadcastScriptType = typeof BROADCAST_SCRIPT_TYPE_OPTIONS[number]['value']

const scriptTypeAliases: Record<string, BroadcastScriptType> = {
  common: '常用广播',
  boarding: '常用广播',
  pre_departure: '常用广播',
  常用: '常用广播',
  常用广播: '常用广播',
  general: '通用广播',
  通用: '通用广播',
  通用广播: '通用广播',
  emergency: '应急广播',
  应急: '应急广播',
  应急广播: '应急广播',
  airport: '机场地名',
  airport_place: '机场地名',
  机场: '机场地名',
  机场地名: '机场地名',
}

function canonicalScriptType(value: string): BroadcastScriptType | undefined {
  return scriptTypeAliases[value.trim().toLocaleLowerCase()]
}

export function normalizeBroadcastScriptType(value: string): BroadcastScriptType {
  return canonicalScriptType(value) || '通用广播'
}

export function broadcastScriptTypeLabel(value: string): string {
  return canonicalScriptType(value) || value
}

export function withBroadcastLanguageSuffix(title: string, language: string): string {
  const suffix = language === 'en_us' ? '英文' : '中文'
  const base = title.trim().replace(/\s*(中文|英文)\s*$/u, '').trimEnd()
  if (!base) return ''
  return `${base.slice(0, 160 - suffix.length)}${suffix}`
}
