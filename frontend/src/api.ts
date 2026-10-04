const TOKEN_KEY = 'st_token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  }
  if (!(options.body instanceof FormData) && options.body) {
    headers['Content-Type'] = 'application/json'
  }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const resp = await fetch(path, { ...options, headers })
  if (resp.status === 401) {
    setToken('')
    if (!path.includes('/auth/')) {
      window.location.hash = '#/login'
    }
    throw new ApiError(401, '登录已过期')
  }
  const text = await resp.text()
  let data: any = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!resp.ok) {
    const msg =
      typeof data === 'object' && data?.detail
        ? typeof data.detail === 'string'
          ? data.detail
          : JSON.stringify(data.detail)
        : `请求失败 (${resp.status})`
    throw new ApiError(resp.status, msg)
  }
  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: any) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: any) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: async (files: File[]): Promise<number[]> => {
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f))
    const res = await request<{ image_ids: number[] }>('/api/wrong-questions/upload', {
      method: 'POST',
      body: fd,
    })
    return res.image_ids
  },
}

/** SSE 流式请求（POST + Bearer），按事件回调 */
export async function streamChat(
  conversationId: number,
  body: { content: string; image_ids: number[] },
  handlers: {
    onMeta?: (d: any) => void
    onDelta: (text: string) => void
    onDone?: (d: any) => void
    onError?: (msg: string) => void
  },
) {
  const resp = await fetch(`/api/chat/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify(body),
  })
  if (!resp.ok || !resp.body) {
    let msg = `请求失败 (${resp.status})`
    try {
      msg = (await resp.json())?.detail || msg
    } catch {}
    handlers.onError?.(msg)
    return
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventName = 'message'
  let dataLines: string[] = []

  const flush = () => {
    if (!dataLines.length) return
    const raw = dataLines.join('\n')
    dataLines = []
    let payload: any = null
    try {
      payload = JSON.parse(raw)
    } catch {}
    if (eventName === 'delta' && payload) handlers.onDelta(payload.content || '')
    else if (eventName === 'meta') handlers.onMeta?.(payload)
    else if (eventName === 'done') handlers.onDone?.(payload)
    else if (eventName === 'error') handlers.onError?.(payload?.message || '未知错误')
    eventName = 'message'
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('event:')) {
        flush()
        eventName = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim())
      } else if (line.trim() === '') {
        flush()
      }
    }
  }
  flush()
}

/** 客户端压缩图片：最长边 1600px，JPEG 输出 */
export async function compressImage(file: File, maxSize = 1600, quality = 0.85): Promise<File> {
  if (!file.type.startsWith('image/')) return file
  try {
    const bitmap = await createImageBitmap(file)
    const scale = Math.min(1, maxSize / Math.max(bitmap.width, bitmap.height))
    const w = Math.round(bitmap.width * scale)
    const h = Math.round(bitmap.height * scale)
    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    ctx.drawImage(bitmap, 0, 0, w, h)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', quality),
    )
    if (!blob) return file
    return new File([blob], file.name.replace(/\.\w+$/, '.jpg'), { type: 'image/jpeg' })
  } catch {
    return file
  }
}
