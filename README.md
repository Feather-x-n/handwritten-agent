# 手写 Agent：DeepSeek 工具调用 + 本地 RAG + 流式 Web 聊天

一个**不依赖 LangChain** 的对话 Agent 完整项目：后端手写 ReAct 循环、工具调用、本地知识库检索和工具安全边界；前端是一个 Vue 3 单页聊天界面，支持流式输出和敏感工具确认。

适合用来理解“大模型 Agent 到底是怎么转起来的”：工具 schema 怎么生成、模型为什么反复调用工具、上下文怎么裁剪、执行权限怎么收口、流式响应怎么落地。

后端细节见 [backen/README.md](backen/README.md)。

## 它能做什么

- 问公司制度（报销、请假、入职、产品 FAQ、运维）→ 检索本地文档，回答并标注“文件名 + 段落号”
- 问数据库数据 → 生成 SELECT 查本地 SQLite（`employees`、`expenses`）
- 让 Agent 写报告 → 写入 `workspace/reports/`，**执行前由用户在网页上点“是/否”**
- 让它看网页 → 只能抓白名单域名，重定向逐跳校验
- 多轮对话、会话持久化、网页上新建/切换/删除会话
- 回复逐字流式显示，中途可以点“停止”

## 技术栈

| 层 | 技术 |
|---|---|
| 模型 | DeepSeek（OpenAI 兼容接口），`deepseek-flash` |
| 后端 | Python 3.10+、FastAPI、Uvicorn、OpenAI SDK、SQLite |
| Agent | 手写 ReAct 循环（无框架）、`@tool` 装饰器、JSON Schema 自动生成 |
| 检索 | 本地 Markdown 语料切段，basic / BM25 / hybrid 三种打分 |
| 前端 | Vue 3 + TypeScript + Vite，axios（REST）+ 原生 fetch（SSE） |

## 架构

```
┌──────────────────────── 浏览器 ────────────────────────┐
│  Vue 3 单页应用（fronten/agent-chat）                  │
│  会话列表 · 流式气泡 · 工具状态 · 是/否确认条 · 停止    │
└───────────────┬───────────────────────────────┬────────┘
                │ REST（axios）                 │ SSE（fetch）
                ▼                               ▼
┌──────────────────── FastAPI（backen/agent/api.py）─────┐
│  /sessions 增删查 · /chat · /chat/stream · /confirm    │
│  SessionStore（SQLite data/app.db）   Trace（JSONL）   │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌──────────────── Agent 循环（agent/runtime.py）──────────┐
│  调模型 → 有 tool_calls 就执行 → 结果塞回上下文 → 再调  │
│  最多 8 步 · 历史裁剪 20 条 · 流式逐 token 产出         │
└───────┬───────────────────────────────┬────────────────┘
        │ tool_calls                    │ 增量事件
        ▼                               ▼
┌──────────────────── 工具层（@tool）─────────────────────┐
│ 时间/天气 · search_docs(RAG) · read_file · write_file   │
│ query_db(只读) · fetch_url(白名单)                      │
│ 路径沙箱 · SQL 只读 · 域名白名单 · 二次确认 · 安全审计   │
└───────────────────────────┬────────────────────────────┘
                            ▼
                 SecurityError → trace 记录 → 如实告知用户
```

## 目录结构

```
PythonProject7/
├─ backen/                     Python 后端
│  ├─ agent/
│  │  ├─ runtime.py            ReAct 循环 + 流式生成器 + 确认回调
│  │  ├─ llm.py                OpenAI 兼容客户端（重试 / 流式）
│  │  ├─ tools.py              @tool 装饰器、注册表、SecurityError
│  │  ├─ builtin_tools.py      时间、天气
│  │  ├─ rag_tools.py          search_docs
│  │  ├─ file_tools.py         路径沙箱、读写文件
│  │  ├─ db_tools.py           SQLite 只读查询
│  │  ├─ web_tools.py          白名单网页抓取
│  │  ├─ memory.py             上下文裁剪
│  │  ├─ traces.py             JSONL 审计
│  │  ├─ store.py              SQLite 会话存储
│  │  ├─ api.py                FastAPI 接口（含 SSE、确认）
│  │  └─ cli.py                命令行入口
│  ├─ rag/                     语料加载、检索打分、评测
│  ├─ docs/                    50 段中文语料（5 份制度/FAQ）
│  ├─ eval/qa.jsonl            22 条评测题
│  ├─ workspace/               文件工具和演示数据库的沙箱目录
│  ├─ data/app.db              会话数据库（运行时生成）
│  └─ README.md                后端详细文档
└─ fronten/
   └─ agent-chat/              Vue 3 前端
      └─ src/
         ├─ App.vue            单页聊天界面（会话、流式渲染、确认条）
         ├─ api/chat.ts        REST + SSE 请求封装
         ├─ utils/request.ts   axios 实例与 get/post/del
         └─ main.ts            应用入口
```

## 快速开始

### 1. 后端

```powershell
cd backen
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env      # 填入 DEEPSEEK_API_KEY 和 DEEPSEEK_URL

python -m uvicorn agent.api:app --port 8000
```

必须在 `backen/` 目录下启动：`docs/`、`data/app.db`、`traces/` 都按当前工作目录查找。

### 2. 前端

```powershell
cd fronten/agent-chat
npm install
npm run dev
```

默认打开 <http://localhost:5173>（Node 要求 `^22.18 || >=24.12`）。后端 CORS 已放行 `5173` / `5174`。

后端地址默认是 `http://127.0.0.1:8000`；要改端口，在 `fronten/agent-chat` 下建 `.env`：

```
VITE_API_BASE=http://127.0.0.1:8011
```

### 3. 验收路径

1. 左侧新建会话，问“报销流程是什么” → 应看到检索来源和流式回答
2. 问“employees 表里有几个人” → 触发 `query_db`
3. 说“把结果写进 reports/demo.md” → 出现黄色确认条，点“是”才落盘，点“否”不创建文件
4. 长回答生成期间点“停止” → 输入框立即解锁，保留已生成内容

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/sessions` | 新建会话 |
| GET | `/sessions` | 会话列表（按更新时间降序） |
| GET | `/sessions/{id}/messages` | 历史消息 |
| DELETE | `/sessions/{id}` | 删除会话及消息 |
| POST | `/sessions/{id}/chat` | 非流式对话 |
| POST | `/sessions/{id}/chat/stream` | SSE 流式对话 |
| GET | `/sessions/{id}/pending` | 是否有待确认工具 |
| POST | `/sessions/{id}/confirm` | 提交“是/否” |

SSE 事件：`token`（正文增量）、`tool_call`（即将调用工具）、`tool_result`、`done`（最终回答）、`error`（流开始后的异常）。

## 流式与工具确认

流式响应是“单向”的，所以项目里两种交互并存：

- **正文/工具事件**：`POST /chat/stream` 建一条 SSE 长连接，后端逐帧推 `data: {...}`
- **用户确认**：是另一个普通请求。Agent 执行 `write_file` 前阻塞，前端每 500ms 轮询 `/pending`，用户点击后 `POST /confirm` 放行；60 秒无响应按拒绝处理

这样模型生成、工具执行、人工审批三条链路互不阻塞，确认框也不会卡住流。

## RAG 评测

`backen/eval/qa.jsonl` 共 22 条（20 条正例 + 2 条无答案负例），命中定义为进入 top3：

| 算法 | recall@3 | top1 | MRR |
|---|---|---|---|
| basic（bigram 覆盖率） | 95% | 70% | 0.817 |
| bm25 | 95% | 80% | 0.867 |
| hybrid（默认） | **100%** | **90%** | **0.942** |

复现：`cd backen && python -m rag.evaluate`

## 安全设计

- **文件**：只允许 `workspace/` 内的相对路径，`resolve()` 后校验，拦 `..` 和越界软链接；读 100KB、写 200KB 上限；写只允许 `.md`
- **数据库**：只读连接、仅 SELECT、限 50 行、2 秒超时
- **出网**：仅 https + 精确域名白名单，最多 3 跳重定向逐跳校验，拒绝非文本响应
- **写操作**：`@tool(confirm=True)` + 确认回调，页面点“是”才执行
- **审计**：每次工具调用、确认、安全拦截都写 JSONL trace

安全边界是**应用层策略**，不是系统级隔离：新工具必须自己调用 `_safe_path` 等检查。

## 声明

> **前端样式说明**：前端项目的界面样式（页面布局、配色、组件外观、CSS）由 **AI 生成**。接口封装、流式解析、确认交互和前后端联调逻辑在此基础上编写与调试。

## 已知限制

- 天气是假数据；时间只支持 4 个固定城市
- 检索只看字面重合，语料只有 50 段，换大语料后 BM25 参数需重新验证
- 无答案阈值（0.2）仅凭 22 条样本观察得出，未硬编码进检索工具
- 前端依赖里仍保留未使用的 `element-plus`、`pinia`、`vue-router`，`src/router/` 为空壳，可以移除
- 同一会话没有并发锁，前端也限制了一次只发一条消息
- 未做 Docker 化和线上部署

## 路线图

1. **部署**：Dockerfile + docker-compose，一条命令起前后端
2. **成本**：上下文裁剪从“按条数”改为“按 token 估算”
3. **评测**：补充工具调用成功率、步数、p95 延迟和 token 成本
4. **工程**：清理前端未用依赖，补 CI 和版本管理
