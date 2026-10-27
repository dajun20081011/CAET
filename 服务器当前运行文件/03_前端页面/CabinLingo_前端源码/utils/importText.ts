export type ImportTextEncoding = 'utf-8' | 'gb18030'

export function decodeImportText(buffer: ArrayBuffer): { text: string; encoding: ImportTextEncoding } {
  const bytes = new Uint8Array(buffer)

  try {
    return {
      text: new TextDecoder('utf-8', { fatal: true }).decode(bytes),
      encoding: 'utf-8',
    }
  } catch {
    try {
      return {
        text: new TextDecoder('gb18030', { fatal: true }).decode(bytes),
        encoding: 'gb18030',
      }
    } catch {
      throw new Error('文件编码无法识别，请另存为 CSV UTF-8 或 GBK 后重试')
    }
  }
}
