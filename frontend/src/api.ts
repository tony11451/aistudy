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
    // 清空凭据后整页重载：让应用状态与路由一起归零，
    // 由路由守卫统一 replace 到登录页（避免把登录页塞进历史）
    if (!path.includes('/auth/')) {
      window.location.reload()
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

/** SSE 流式请求（POST + Bearer），按事件回调（v4：支持 skill/change 事件） */
export async function streamChat(
  conversationId: number,
  body: { content: string; image_ids: number[]; model?: string },
  handlers: {
    onMeta?: (d: any) => void
    onDelta: (text: string) => void
    onSkill?: (d: { name: string; status: string; summary?: string; args?: any }) => void
    onChange?: (d: { change_id?: number; description: string; reason?: string; action?: string }) => void
    onDone?: (d: any) => void
    onError?: (msg: string) => void
  },
) {
  // 流空闲超时（v5 修复）：90 秒无数据视为中断，避免「一直转圈」
  const controller = new AbortController()
  let idleTimer: ReturnType<typeof setTimeout> | null = null
  const bumpIdle = () => {
    if (idleTimer) clearTimeout(idleTimer)
    idleTimer = setTimeout(() => controller.abort(), 90_000)
  }
  let resp: Response
  try {
    bumpIdle()
    resp = await fetch(`/api/chat/conversations/${conversationId}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
  } catch (e: any) {
    if (idleTimer) clearTimeout(idleTimer)
    handlers.onError?.(e?.name === 'AbortError' ? 'AI 响应超时，请重试' : '网络异常，请重试')
    return
  }
  if (!resp.ok || !resp.body) {
    if (idleTimer) clearTimeout(idleTimer)
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
  let finished = false

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
    else if (eventName === 'skill') handlers.onSkill?.(payload)
    else if (eventName === 'change') handlers.onChange?.(payload)
    else if (eventName === 'done') {
      finished = true
      handlers.onDone?.(payload)
    } else if (eventName === 'error') {
      finished = true
      handlers.onError?.(payload?.message || '未知错误')
    }
    eventName = 'message'
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      bumpIdle()
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
    // done/error 必达：流意外结束时也要解锁界面
    if (!finished) {
      handlers.onError?.('连接中断，回答可能不完整，请重试')
    }
  } catch (e: any) {
    if (!finished) {
      handlers.onError?.(e?.name === 'AbortError' ? 'AI 响应超时，请重试' : '网络中断，请重试')
    }
  } finally {
    if (idleTimer) clearTimeout(idleTimer)
  }
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

/** v4：供应商 / 变更 / 数据迁移 */
export const providersApi = {
  list: () => api.get<any>('/api/providers'),
  create: (body: any) => api.post<any>('/api/providers', body),
  update: (id: number, body: any) => api.put<any>(`/api/providers/${id}`, body),
  remove: (id: number) => api.del(`/api/providers/${id}`),
  setCurrent: (modelRef: string) => api.put('/api/providers/current/model', { model_ref: modelRef }),
}

export const changesApi = {
  list: (limit = 50) => api.get<any[]>(`/api/changes?limit=${limit}`),
  undo: (id: number) => api.post<any>(`/api/changes/${id}/undo`),
}

export const dataApi = {
  exportUrl: (scope: 'personal' | 'full') => `/api/data/export?scope=${scope}`,
  exportDownload: async (scope: 'personal' | 'full') => {
    const resp = await fetch(dataApi.exportUrl(scope), {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
    if (!resp.ok) throw new Error('导出失败')
    return resp.blob()
  },
  importFile: async (scope: 'personal' | 'full', file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<any>(`/api/data/import?scope=${scope}`, { method: 'POST', body: fd })
  },
}

/** v5：档案库 */
export const libraryApi = {
  overview: (subject = '') =>
    api.get<any>(`/api/library/overview${subject ? `?subject=${encodeURIComponent(subject)}` : ''}`),
  search: (params: { q?: string; subject?: string; kind?: string; source?: string; limit?: number }) => {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&')
    return api.get<any>(`/api/library/items${qs ? `?${qs}` : ''}`)
  },
  getItem: (id: number) => api.get<any>(`/api/library/items/${id}`),
  updateItem: (id: number, body: any) => api.put<any>(`/api/library/items/${id}`, body),
  deleteItem: (id: number) => api.del(`/api/library/items/${id}`),
  moveItem: (id: number, body: any) => api.put<any>(`/api/library/items/${id}`, body),
  linkItem: (id: number, boardId: number) => api.post(`/api/library/items/${id}/link`, { board_id: boardId }),
  uploadItems: async (files: File[], opts: { subject?: string; kind?: string; board_id?: number; book_id?: number; page_no?: number }) => {
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f))
    const qs = Object.entries(opts)
      .filter(([, v]) => v !== undefined && v !== '' && v !== 0)
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&')
    return request<any>(`/api/library/items/upload${qs ? `?${qs}` : ''}`, { method: 'POST', body: fd })
  },
  createTextItem: (body: any) => api.post<any>('/api/library/items/text', body),
  downloadUrl: (id: number) => `/api/library/items/${id}/download`,
  download: async (id: number, filename: string) => {
    const resp = await fetch(libraryApi.downloadUrl(id), {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
    if (!resp.ok) throw new Error('下载失败')
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },
  // 书本
  createBook: (body: any) => api.post<any>('/api/library/books', body),
  updateBook: (id: number, body: any) => api.put<any>(`/api/library/books/${id}`, body),
  deleteBook: (id: number) => api.del(`/api/library/books/${id}`),
  bookPages: (id: number) => api.get<any>(`/api/library/books/${id}/pages`),
  addPage: async (bookId: number, file: File, pageNo = 0) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<any>(`/api/library/books/${bookId}/pages?page_no=${pageNo}`, {
      method: 'POST',
      body: fd,
    })
  },
  // 板块
  boards: (subject = '') =>
    api.get<any[]>(`/api/library/boards${subject ? `?subject=${encodeURIComponent(subject)}` : ''}`),
  createBoard: (body: any) => api.post<any>('/api/library/boards', body),
  boardTemplates: (id: number) => api.post<any>(`/api/library/boards/${id}/templates`, {}),
  updateBoard: (id: number, body: any) => api.put<any>(`/api/library/boards/${id}`, body),
  deleteBoard: (id: number) => api.del(`/api/library/boards/${id}`),
  // 书签 / OCR
  bookmarks: () => api.get<any[]>('/api/library/bookmarks'),
  addBookmark: (body: any) => api.post<any>('/api/library/bookmarks', body),
  deleteBookmark: (id: number) => api.del(`/api/library/bookmarks/${id}`),
  runOcr: () => api.post<any>('/api/library/ocr/run', {}),
}
