const DATABASE_NAME = 'cabinlingo-prosody-studio'
const DATABASE_VERSION = 1
const STORE_NAME = 'projects'

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) request.result.createObjectStore(STORE_NAME)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('无法打开本机制作记录存储。'))
  })
}

export async function loadProsodyProject<T>(key: string): Promise<T | null> {
  if (!key || !('indexedDB' in window)) return null
  const database = await openDatabase()
  try {
    return await new Promise<T | null>((resolve, reject) => {
      const request = database.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME).get(key)
      request.onsuccess = () => resolve((request.result as T | undefined) || null)
      request.onerror = () => reject(request.error || new Error('无法读取本机制作记录。'))
    })
  } finally { database.close() }
}

export async function saveProsodyProject<T>(key: string, project: T): Promise<void> {
  if (!key || !('indexedDB' in window)) throw new Error('当前浏览器不支持本机制作记录存储。')
  const database = await openDatabase()
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, 'readwrite')
      transaction.objectStore(STORE_NAME).put(project, key)
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error || new Error('无法保存本机制作记录。'))
      transaction.onabort = () => reject(transaction.error || new Error('本机制作记录保存已中止。'))
    })
  } finally { database.close() }
}

export async function deleteProsodyProject(key: string): Promise<void> {
  if (!key || !('indexedDB' in window)) return
  const database = await openDatabase()
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, 'readwrite')
      transaction.objectStore(STORE_NAME).delete(key)
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error || new Error('无法清除本机制作记录。'))
      transaction.onabort = () => reject(transaction.error || new Error('本机制作记录清除已中止。'))
    })
  } finally { database.close() }
}
