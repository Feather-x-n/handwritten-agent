import { baseURL, get, post } from '../utils/request'

// 后端保存的一条消息（页面只需要 role 和 content）
export interface ChatMessage {
  role: string
  content?: string | null
}

// 等待用户确认的工具调用
export interface PendingConfirm {
  id: string
  name: string
  args: Record<string, unknown>
}

// 给某个会话发一条消息，后端返回这一轮之后的完整消息列表
export function chatapi(sessionId: string, message: string) {
  return post<{ messages: ChatMessage[] }>(`/sessions/${encodeURIComponent(sessionId)}/chat`, {
    message,
  })
}

// 查询当前有没有等着确认的敏感工具
export function getPending(sessionId: string) {
  return get<{ pending: PendingConfirm | null }>(`/sessions/${encodeURIComponent(sessionId)}/pending`)
}

// 把用户的选择告诉后端：true = 允许执行，false = 拒绝
export function confirmTool(sessionId: string, confirmId: string, approved: boolean) {
  return post<{ ok: boolean; approved: boolean }>(`/sessions/${encodeURIComponent(sessionId)}/confirm`, {
    confirm_id: confirmId,
    approved,
  })
}

// 后端 SSE 推过来的事件，和后端 Agent.stream 的 event 一一对应
export interface StreamEvent {
  type: 'token' | 'tool_call' | 'tool_result' | 'done' | 'error'
  text?: string // token / done 的正文
  name?: string // tool_call / tool_result 的工具名
  args?: Record<string, unknown>
  result?: string
  message?: string // error 的错误信息
  tokens?: number
  id?: string
}

// axios 在浏览器里拿不到增量数据，流式必须用原生 fetch
export async function chatStream(
  sessionId: string,
  message: string,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${baseURL}/sessions/${encodeURIComponent(sessionId)}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ message }),
    signal,
  })

  // 只有“开始返回流之前”的错误才有正常的 HTTP 状态码和 detail
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      // 响应不是 JSON 就保留状态码
    }
    throw new Error(detail)
  }
  if (!res.body) throw new Error('当前浏览器不支持流式响应')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    buffer = buffer.replace(/\r\n/g, '\n')

    // SSE 事件以空行分隔，最后一段可能不完整，留在 buffer 里等下一次
    let cut = buffer.indexOf('\n\n')
    while (cut >= 0) {
      const block = buffer.slice(0, cut)
      buffer = buffer.slice(cut + 2)
      const data = block
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n')
      if (data) {
        try {
          onEvent(JSON.parse(data) as StreamEvent)
        } catch {
          // 坏帧直接忽略，不影响后面的消息
        }
      }
      cut = buffer.indexOf('\n\n')
    }
  }
}
