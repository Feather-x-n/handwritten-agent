<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { del, get, post } from './utils/request'
import { chatStream, confirmTool, getPending, type ChatMessage, type PendingConfirm } from './api/chat'

// 后端返回的数据结构
interface Session {
  id: string
  title: string
}

// 页面状态
const sessions = ref<Session[]>([]) // 左侧会话列表
const currentId = ref('') // 当前会话 id
const messages = ref<{ role: 'user' | 'assistant'; content: string }[]>([]) // 右侧消息
const input = ref('') // 输入框内容
const sending = ref(false) // 是否正在等回复
const errorMsg = ref('') // 错误提示
const pending = ref<PendingConfirm | null>(null) // 正在等用户确认的敏感工具
const hasToken = ref(false) // 这一轮是否已经收到正文
const toolHint = ref('') // 正在执行哪个工具
let streamController: AbortController | null = null // 用来中止这条流

// 气泡下方的一行状态提示：等确认 > 调工具 > 思考中 > 没内容就不显示
const statusText = computed(() => {
  if (!sending.value) return ''
  if (pending.value) return '等待你确认…'
  if (toolHint.value) return toolHint.value
  return hasToken.value ? '' : '思考中…'
})

// 后端消息 -> 页面消息：只保留用户和助手说的文字
function toView(list: ChatMessage[]) {
  return list
    .filter((m) => (m.role === 'user' || m.role === 'assistant') && m.content?.trim())
    .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content as string }))
}

// 滚到消息区底部
async function scrollToBottom() {
  await nextTick()
  const el = document.querySelector<HTMLElement>('.messages')
  if (el) el.scrollTop = el.scrollHeight
}

// ========== 会话操作 ==========
async function loadSessions() {
  const data = await get<{ sessions: Session[] }>('/sessions')
  sessions.value = data.sessions ?? []
}

async function openSession(id: string) {
  if (!id || sending.value) return
  currentId.value = id
  messages.value = []
  errorMsg.value = ''
  try {
    const data = await get<{ messages: ChatMessage[] }>(`/sessions/${encodeURIComponent(id)}/messages`)
    if (id === currentId.value) messages.value = toView(data.messages ?? [])
    await scrollToBottom()
  } catch (e) {
    errorMsg.value = `加载消息失败：${(e as Error).message}`
  }
}

async function createSession() {
  try {
    const data = await post<{ id: string }>('/sessions', { title: '新会话' })
    await loadSessions()
    await openSession(data.id)
  } catch (e) {
    errorMsg.value = `新建会话失败：${(e as Error).message}`
  }
}

async function removeSession(id: string) {
  if (sending.value) return
  if (!window.confirm('删除这个会话以及它的全部消息？')) return
  try {
    await del(`/sessions/${encodeURIComponent(id)}`)
    await loadSessions()
    if (id === currentId.value) {
      currentId.value = ''
      messages.value = []
      const first = sessions.value[0]
      if (first) await openSession(first.id)
    }
  } catch (e) {
    errorMsg.value = `删除会话失败：${(e as Error).message}`
  }
}

// ========== 敏感工具确认 ==========
// 等回复期间不停问后端“有没有要我确认的工具”，有就显示是/否按钮
let watchToken = 0
async function watchPending(id: string) {
  const token = ++watchToken
  while (sending.value && token === watchToken && id === currentId.value) {
    try {
      const data = await getPending(id)
      if (token !== watchToken) return
      if (data.pending) {
        pending.value = data.pending
        return
      }
    } catch {
      return // 后端还没提供 /pending 接口时直接停止，不影响正常聊天
    }
    await new Promise((r) => setTimeout(r, 500))
  }
}

// 用户点了“是”或“否”
async function answer(approved: boolean) {
  const p = pending.value
  const id = currentId.value
  if (!p || !id) return

  pending.value = null
  try {
    await confirmTool(id, p.id, approved)
  } catch (e) {
    errorMsg.value = `确认失败：${(e as Error).message}`
    return
  }
  // 同一回合里可能还有下一个敏感工具，继续监听
  if (sending.value) void watchPending(id)
}

// ========== 发送消息 ==========
function stop() {
  streamController?.abort() // 中止读流，后端的生成器也会随之关闭
}

async function send() {
  const text = input.value.trim()
  const id = currentId.value
  if (!text || !id || sending.value) return

  sending.value = true
  hasToken.value = false
  toolHint.value = ''
  errorMsg.value = ''
  input.value = ''
  messages.value.push({ role: 'user', content: text }) // 先把用户消息显示出来

  // 先放一个空的助手气泡，token 到了往里面追加。
  // 必须从数组里取（拿到的是响应式代理），改外面的普通对象页面不会更新
  const index = messages.value.push({ role: 'assistant', content: '' }) - 1
  const answer = messages.value[index]
  if (!answer) return

  streamController = new AbortController()
  void watchPending(id) // 同时监听敏感工具确认

  try {
    await chatStream(
      id,
      text,
      (e) => {
        if (id !== currentId.value) return // 用户切了会话，就不再改当前界面
        if (e.type === 'token') {
          answer.content += e.text ?? ''
          hasToken.value = true
          toolHint.value = ''
        } else if (e.type === 'tool_call') {
          toolHint.value = `正在调用 ${e.name}…`
        } else if (e.type === 'tool_result') {
          toolHint.value = ''
        } else if (e.type === 'done') {
          answer.content = e.text ?? answer.content // 以完整答案为准，防止丢字
          hasToken.value = true
        } else if (e.type === 'error') {
          errorMsg.value = `出错：${e.message}`
        }
        void scrollToBottom()
      },
      streamController.signal,
    )
    void loadSessions() // 刷新左侧列表的更新时间排序
  } catch (e) {
    // 用户主动点“停止”不算错误
    if ((e as Error).name !== 'AbortError') {
      errorMsg.value = `发送失败：${(e as Error).message}`
    }
  } finally {
    // 一个字都没收到就失败了，把空气泡清掉
    if (!answer.content.trim()) {
      messages.value = messages.value.filter((m) => m !== answer)
    }
    sending.value = false
    pending.value = null
    toolHint.value = ''
    hasToken.value = false
    streamController = null
    await scrollToBottom()
  }
}

// 回车发送；中文输入法选词时的回车不算
function onEnter(e: KeyboardEvent) {
  if (e.isComposing) return
  e.preventDefault()
  if (!sending.value && input.value.trim()) void send()
}

// 打开页面时：加载会话列表，并打开第一个会话
onMounted(async () => {
  try {
    await loadSessions()
    const first = sessions.value[0]
    if (first) await openSession(first.id)
  } catch (e) {
    errorMsg.value = `获取会话列表失败：${(e as Error).message}`
  }
})
</script>

<template>
  <div class="app">
    <!-- 左侧：会话列表 -->
    <aside class="sidebar">
      <strong>手写 Agent</strong>
      <button :disabled="sending" @click="createSession">＋ 新建会话</button>
      <p v-if="!sessions.length" class="hint">还没有会话</p>
      <div
        v-for="s in sessions"
        :key="s.id"
        class="session"
        :class="{ active: s.id === currentId }"
        @click="openSession(s.id)"
      >
        {{ s.title || '未命名会话' }}
        <!-- .stop：点删除时不要顺带切换会话 -->
        <span class="del" @click.stop="removeSession(s.id)">×</span>
      </div>
    </aside>

    <!-- 右侧：聊天区 -->
    <main class="chat">
      <div v-if="errorMsg" class="error">{{ errorMsg }}</div>

      <div class="messages">
        <p v-if="!currentId" class="hint">先在左侧新建或选择一个会话</p>
        <p v-else-if="!messages.length && !sending" class="hint">还没有消息，说点什么吧</p>

        <div v-for="(m, i) in messages" :key="i" class="row" :class="m.role">
          <span class="avatar">{{ m.role === 'user' ? '我' : 'AI' }}</span>
          <div class="bubble">{{ m.content }}</div>
        </div>

        <p v-if="statusText" class="hint">{{ statusText }}</p>
      </div>

      <!-- 敏感工具确认：用户点“是”才执行，“否”则跳过 -->
      <div v-if="pending" class="confirm">
        <div class="confirm-text">
          <strong>要执行 {{ pending.name }} 吗？</strong>
          <code>{{ JSON.stringify(pending.args) }}</code>
        </div>
        <div class="confirm-actions">
          <button class="yes" @click="answer(true)">是</button>
          <button class="no" @click="answer(false)">否</button>
        </div>
      </div>

      <div class="composer">
        <textarea
          v-model="input"
          rows="2"
          :disabled="!currentId"
          placeholder="输入消息，Enter 发送，Shift + Enter 换行"
          @keydown.enter="onEnter"
        ></textarea>
        <!-- 流式输出期间按钮变成“停止”，免得模型卡住时页面一直锁着 -->
        <button v-if="!sending" :disabled="!currentId || !input.trim()" @click="send">发送</button>
        <button v-else class="stop" @click="stop">停止</button>
      </div>
    </main>
  </div>
</template>

<style>
/* 全局：铺满窗口、去掉默认边距 */
html,
body,
#app {
  height: 100%;
  margin: 0;
}
body {
  background: #eef1f7;
  color: #1f2430;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
* {
  box-sizing: border-box;
}
</style>

<style scoped>
/* 整体：左栏 240px，右栏自适应 */
.app {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  height: 100dvh;
}

/* 通用按钮样式 */
button {
  border: 0;
  border-radius: 8px;
  background: #2f6bff;
  color: #fff;
  font: inherit;
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 左侧：会话列表 */
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  padding: 14px;
  overflow-y: auto;
  background: #fff;
  border-right: 1px solid #e3e8f0;
}
.sidebar button {
  padding: 8px;
}
.session {
  position: relative;
  padding: 8px 24px 8px 10px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
}
.session:hover {
  background: #f4f7fd;
}
.session.active {
  background: #eaf1ff;
  color: #2f6bff;
}
/* 删除按钮：平时隐藏，鼠标移到会话上才出现 */
.del {
  position: absolute;
  top: 6px;
  right: 8px;
  color: #7b8494;
  opacity: 0;
}
.session:hover .del {
  opacity: 1;
}
.del:hover {
  color: #d64545;
}

/* 右侧：聊天区 */
.chat {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: #f6f8fc;
}
.hint {
  color: #7b8494;
  font-size: 13px;
  text-align: center;
}
.error {
  padding: 8px 16px;
  background: #fff1f1;
  color: #b53737;
  font-size: 13px;
}

/* 消息气泡：用户靠右、助手靠左 */
.row {
  display: flex;
  gap: 8px;
  max-width: 880px;
  margin: 0 auto 12px;
}
.row.user {
  flex-direction: row-reverse;
}
.avatar {
  flex: none;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: #e8eefc;
  color: #2f6bff;
  font-size: 12px;
}
.row.user .avatar {
  background: #2f6bff;
  color: #fff;
}
.bubble {
  max-width: 78%;
  padding: 9px 13px;
  border: 1px solid #e3e8f0;
  border-radius: 12px;
  background: #fff;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.row.user .bubble {
  background: #2f6bff;
  border-color: #2f6bff;
  color: #fff;
}

/* 敏感工具确认条 */
.confirm {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  background: #fff8e6;
  border-top: 1px solid #f0d9a0;
  font-size: 13px;
}
.confirm-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.confirm-text code {
  overflow: hidden;
  color: #8a6d1a;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.confirm-actions {
  display: flex;
  flex: none;
  gap: 8px;
}
.confirm-actions button {
  padding: 6px 14px;
}
.confirm-actions .yes {
  background: #e6a100;
}
.confirm-actions .no {
  background: #8b93a1;
}

/* 底部：输入框 + 发送按钮 */
.composer {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: #fff;
  border-top: 1px solid #e3e8f0;
}
.composer textarea {
  flex: 1;
  padding: 8px 10px;
  border: 1px solid #d8dfec;
  border-radius: 8px;
  font: inherit;
  resize: none;
  outline: none;
}
.composer textarea:focus {
  border-color: #9dbcff;
}
.composer button {
  padding: 0 18px;
}
.composer .stop {
  background: #8b93a1;
}
</style>
