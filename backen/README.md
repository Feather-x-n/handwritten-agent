# 手写 Agent（DeepSeek 工具调用 + 本地 RAG + 工具安全）

不用 LangChain 等框架，手写 ReAct 循环的对话 Agent：模型需要调工具就执行，把结果塞回上下文，直到给出最终回答。工具覆盖时间/天气、本地文档检索（RAG）、工作区文件读写、SQLite 只读查询和白名单网页抓取，每一步都有边界和审计。

后端同时提供 CLI 和 FastAPI 接口：会话落 SQLite，回复支持 SSE 流式输出，敏感工具通过确认回调暂停、等待前端点“是/否”后继续。

完整项目（含 Vue 前端）的说明见上级目录的 [README.md](../README.md)。

## 功能

- **工具调用**：`@tool` 装饰器从函数签名和 docstring 自动生成 JSON Schema，新增工具只写函数
- **多轮工具**：模型的单次回复可以包含多个工具调用，依次执行后继续循环，单轮最多 8 步
- **流式输出**：`Agent.stream` 逐 token 产出正文，并额外推送工具调用/工具结果事件，接口层转成 SSE
- **自动重试**：429 / 超时 / 连接失败 / 5xx 最多重试 5 次，间隔 1s、2s、4s、8s；400 / 401 直接失败，不浪费钱。流式请求只重试“首包之前”，避免用户看到重复文字
- **上下文裁剪**：发给模型的历史超过 20 条自动截断，始终保留 system，并丢弃开头悬空的 `tool` 消息，避免 `tool_calls` 配对被切断导致 400
- **会话持久化**：SQLite 存会话和消息（`data/app.db`），支持新建、列表、读取、删除；流式/非流式回复结束后统一落库
- **全链路 trace**：每轮对话写一份 JSONL，包含用户输入、工具调用、工具返回、确认结果、安全拦截和模型回答
- **本地文档检索**：50 段中文语料，bigram / BM25 / 单字混合三种打分，`search_docs` 返回 top3 并强制模型标注来源
- **工具安全**：文件路径白名单、SQLite 只读、写操作二次确认、查询超时、HTTP 域名白名单 + 逐跳重定向校验
- **可量化**：22 条评测题（20 正例 + 2 无答案负例），当前 recall@3 100%、top1 90%、MRR 0.942

## 目录结构

```
agent/
  config.py         环境变量、模型名、MAX_STEP、MAX_MESSAGES、白名单、system prompt
  llm.py            OpenAI 兼容客户端封装 + 重试（含流式）
  tools.py          @tool 装饰器、工具注册表、SecurityError
  builtin_tools.py  内置工具：当前时间、天气
  rag_tools.py      文档检索工具 search_docs
  file_tools.py     工作区文件读写：路径沙箱、大小上限、写报告
  db_tools.py       SQLite 只读查询：mode=ro、SELECT-only、行数与时间上限
  web_tools.py      HTTP 抓取：https + 域名白名单、重定向逐跳校验、响应截断
  memory.py         上下文裁剪
  traces.py         JSONL trace 写入
  runtime.py        Agent 主循环、流式生成器、确认回调、安全事件记录
  store.py          SQLite 会话/消息存储
  api.py            FastAPI 接口：会话管理、普通对话、SSE、确认
  cli.py            命令行入口
rag/
  loader.py         读取 docs/*.md，按空行切段（source / index / text）
  search.py         打分与排序：basic、BM25、单字+bigram 混合
  evaluate.py       评测脚本：recall@3、top1、MRR
docs/               语料：报销、请假、产品 FAQ、入职指南、部署运维，共 5 份 50 段
eval/qa.jsonl       20 道正例 + 2 道无答案负例
workspace/
  data/company.db   演示数据库：employees（8 人）、expenses（10 条）
  reports/          报告输出目录（write_file 只能写这里，首次写入时创建）
  notes/            普通笔记目录
data/app.db         运行时生成的会话数据库
traces/             运行后生成的 trace 文件
```

## 快速开始

要求 Python 3.10+。**以下命令都在 `backen/` 目录下执行**——`data/app.db`、`docs/` 和 `traces/` 都是相对工作目录的路径。

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env      # 然后填入自己的 key 和 base_url

python -m agent.cli                    # 命令行对话（确认时输入 y）
python -m rag.search "报销流程"        # 单查询检索，看 top3
python -m rag.evaluate                 # 跑评测

python -m uvicorn agent.api:app --port 8000   # HTTP 接口
```

接口启动后：

- Swagger：<http://127.0.0.1:8000/docs>
- 前端默认请求 `http://127.0.0.1:8000`，启动方式见根目录 README

## HTTP 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/sessions` | 新建会话，body：`{"title": "新会话"}`，返回 `{"id": ...}` |
| GET | `/sessions` | 会话列表，按 `updated_at` 降序 |
| GET | `/sessions/{id}/messages` | 读取历史消息（OpenAI 格式） |
| DELETE | `/sessions/{id}` | 删除会话及其全部消息 |
| POST | `/sessions/{id}/chat` | 非流式对话，返回这一轮之后的完整消息列表 |
| POST | `/sessions/{id}/chat/stream` | 流式对话，返回 `text/event-stream` |
| GET | `/sessions/{id}/pending` | 当前是否有等待确认的敏感工具 |
| POST | `/sessions/{id}/confirm` | 提交确认结果，body：`{"confirm_id": "...", "approved": true}` |

### SSE 事件

`/chat/stream` 每帧格式为 `data: {JSON}\n\n`：

| type | 字段 | 含义 |
|---|---|---|
| `token` | `text` | 模型正文增量 |
| `tool_call` | `name`、`args`、`id` | 即将执行某个工具 |
| `tool_result` | `name`、`result` | 工具返回值 |
| `done` | `text`、`tokens` | 本轮最终回答 |
| `error` | `message` | 流开始后的异常（此时 HTTP 状态码已经是 200，只能通过事件传递） |

### 敏感工具确认

`write_file` 标记了 `@tool(confirm=True)`。走 API 时：

1. Agent 执行到该工具前调用 `make_confirm(session_id)` 生成的回调，登记一条待确认记录并阻塞
2. 前端轮询 `/pending` 拿到 `{id, name, args}`，显示确认按钮
3. 前端 POST `/confirm`；`approved=true` 才真正执行，`false` 返回“用户拒绝执行该操作”
4. 60 秒没有响应按拒绝处理；流式连接在等待期间保持打开

CLI 模式不传确认回调，`runtime._confirm` 回退为终端 `input()`，输入 `y` 才继续。

## 配置

`.env` 里两项：

| 变量 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | API key |
| `DEEPSEEK_URL` | OpenAI 兼容接口的 base_url |

其余在 `agent/config.py`：

| 配置 | 默认值 | 说明 |
|---|---|---|
| `MODEL` | `deepseek-flash` | 模型名 |
| `MAX_STEP` | 8 | 单轮最多工具步数 |
| `MAX_MESSAGES` | 20 | 发给模型的历史条数上限 |
| `ALLOWED_HOSTS` | `example.com`、`docs.python.org` | HTTP 抓取的域名白名单 |
| `HTTP_TIMEOUT` / `HTTP_MAX_BYTES` / `HTTP_MAX_CHARS` | 5s / 200KB / 4000 | 抓取超时、字节与字符上限 |

## 工具与安全边界

| 工具 | 作用 | 边界 |
|---|---|---|
| `get_current_time` | 北京/上海/纽约/伦敦当前时间 | 仅 4 个固定城市 |
| `get_weather` | 上述城市天气，支持摄氏/华氏 | 演示用假数据 |
| `search_docs` | 检索 `docs/` 并返回 top3 全文 | 只查本地语料 |
| `read_file` | 读取工作区文本文件 | 仅 `workspace/`、≤100KB、UTF-8 |
| `write_file` | 把报告写入 `workspace/reports/` | 仅 `.md`、≤200KB、**需用户确认** |
| `query_db` | 查询 `workspace/data/` 下的 SQLite | 只读连接、仅 SELECT、≤50 行、≤2 秒 |
| `fetch_url` | 抓取白名单网站的网页正文 | 仅 https、精确域名、逐跳校验重定向、≤200KB |

安全策略的实现位置：

- **路径沙箱**（`file_tools._safe_path`）：拒绝绝对路径和 `..`，`resolve()` 后用 `is_relative_to` 兜底，指向工作区外的软链接也会被拦
- **数据库**（`db_tools`）：`mode=ro` 只读连接、关键字黑名单 + 单语句检查、`fetchmany(51)` 限行、`set_progress_handler` 检查 deadline（无限递归 CTE 2 秒内中断）
- **二次确认**（`@tool(confirm=True)` + `runtime._confirm`）：CLI 输入 `y` 才执行；API 走 `/pending` + `/confirm` 回调，拒绝、超时、EOF 都按取消处理
- **出网**（`web_tools._check_url`）：只允许 https、443 端口，禁止 URL 内嵌账号密码，主机名精确匹配白名单；重定向手动逐跳校验，最多 3 跳；非文本 Content-Type 直接拒绝
- **安全审计**：工具抛出 `SecurityError` 时，`runtime` 记录一条 `security` 事件，模型收到错误说明后如实告知用户

新增工具只需要写一个带 docstring 和类型注解的函数：

```python
from .tools import tool

@tool
def get_weather(city: str, unit: str = "celsius") -> str:
    """查询城市实时天气。"""
```

有默认值的参数自动变成非必填；没写 docstring 的工具模型基本不会调用；危险工具加 `@tool(confirm=True)`。

## 文档检索（RAG）

```
docs/*.md ─ load_chunks ─> 50 个段落（source/index/text）
                              │
用户问题 ─ search(q, top_k=3) ─> top3 段落 ─ search_docs ─> 模型回答（标注文件名 + 段号）
```

- **切分**：按空行切段，段号从 1 开始；`search_docs` 把 top3 的完整段落一起返回，不再单独提供“读原文”的工具——单段只有 100 多字，多一步调用不划算。
- **打分**（`rag/search.py`，`method` 参数可切换）：

| 算法 | 思路 | recall@3 | top1 | MRR |
|---|---|---|---|---|
| `basic` | query 的 bigram 有多大比例出现在段落里 | 95% | 70% | 0.817 |
| `bm25` | IDF + 词频 + 长度归一化 | 95% | 80% | 0.867 |
| `hybrid`（默认） | BM25 的 bigram 与单字各占 50% | **100%** | **90%** | **0.942** |

- **评测**（`rag/evaluate.py`）：`eval/qa.jsonl` 共 22 条，20 条正例题标注期望的 `source + index`，命中定义为进入 top3；另 2 条无答案题只打印 top1 分数，人工判断。负面题当前最高分 0.16，正例 top1 最低 0.254，阈值 0.2 能分开，但样本太少，还没有硬编码进工具。
- **引用**：`search_docs` 返回的每条结果都带 `文档：文件名，段落索引：N`，`SYSTEM_PROMPT` 要求模型回答时必须标注来源，检索不到就直说没找到。

## trace 示例

每次启动生成 `traces/2026-10-29_20-15-57.jsonl`，一行一个事件：

```json
{"kind": "user", "text": "帮我看看 https://evil.com/x 这个页面写了什么", "time": "2026-10-29 20:15:57"}
{"kind": "assistant_tool_call", "tool_calls": [{"name": "fetch_url", "args": "{\"url\": \"https://evil.com/x\"}"}], "tokens": 1113, "step": 1, "time": "2026-10-29 20:15:59"}
{"kind": "security", "tool": "fetch_url", "args": {"url": "https://evil.com/x"}, "reason": "不允许的 URL 主机: evil.com", "time": "2026-10-29 20:15:59"}
{"kind": "tool", "name": "fetch_url", "args": {"url": "https://evil.com/x"}, "result": "错误：不允许的 URL 主机: evil.com", "time": "2026-10-29 20:15:59"}
{"kind": "assistant_answer", "text": "我没法帮你读取这个页面。抓取请求被拒绝了……", "tokens": 1213, "time": "2026-10-29 20:16:01"}
```

写文件时会多一条确认事件（`approved` 为 `true` 才真正执行）：

```json
{"kind": "confirm", "tool": "write_file", "args": {"filename": "daily.md", "content": "..."}, "approved": true, "time": "2026-10-29 17:35:36"}
```

事件类型：`user`、`assistant_tool_call`、`tool`、`assistant_answer`、`trim`、`retry`、`confirm`、`security`。

## 已知限制

- 天气是假数据，时间只支持 4 个固定城市
- 检索只看字面重合，不理解同义词；“发票”能命中“票据”主要靠单字匹配
- 语料只有 50 段，BM25 的 IDF 统计量很小，换成大语料后参数需要重新验证
- 无答案判定没有自动阈值，目前靠人工看分数
- HTTP 白名单要在 `config.py` 手动维护；不解析 HTML（返回原始文本）；不防 DNS 重绑定（白名单域名解析到内网 IP 的情况）；畸形 IPv6 地址会被记成普通错误而不是 `security` 事件
- 文件与数据库沙箱是**应用层策略**，不是系统级隔离：进程仍以当前用户权限运行，新工具必须自己调用 `_safe_path`，否则会绕开边界
- 裁剪按消息条数，不按 token
- 模型客户端是同步的，接口层靠 FastAPI 线程池承载；同一个会话没有并发锁，不要同时发两条消息
- 等待确认的连接最多挂 60 秒，超时按拒绝处理

## 下一步

1. Docker 化：后端 + 前端一条命令启动，环境变量注入 key
2. 裁剪改为按 token 估算，降低长对话成本
3. 扩充评测集：工具调用成功率、步数、p95 延迟和成本统计
4. 会话级并发控制（同一会话串行处理）
