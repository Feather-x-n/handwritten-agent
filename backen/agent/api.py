from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .config import SYSTEM_PROMPT
from .llm import LLMClient
from .runtime import Agent
from .store import SessionStore
from .traces import Trace
from .tools import get_schemas, get_impls
from fastapi.middleware.cors import CORSMiddleware
import json
from fastapi.responses import StreamingResponse
from . import rag_tools
from . import builtin_tools
from . import file_tools
from . import db_tools
from . import web_tools
import threading
import uuid
app = FastAPI(title="手写 Agent API")
store = SessionStore()
client = LLMClient()          # 无状态，可全局共用
schemas = get_schemas()
impls = get_impls()
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
#创建新绘话
class CreateSession(BaseModel):
    title: str = "新会话"

#封装对话消息
class ChatIn(BaseModel):
    message: str
# 等待用户确认的工具调用：confirm_id -> 记录
WAITING:dict[str,dict] = {}
WAITING_LOCK = threading.Lock()
CONFIRM_TIMEOUT = 60 
#配置sse相关功能
def _sse(event: dict) -> str:
    """把一个事件编码成 SSE 帧：data: {...}\\n\\n"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
#确定工具按钮
def make_confirm(session_id:str):
    """给 Agent 用的 confirm 回调：敏感工具先挂起，等前端点按钮,闭包返回confirm"""
    def confirm(name:str,args:dict)->bool:
        #加密确认id
        confirm_id = uuid.uuid4().hex[:8]
        record = {
            "session_id": session_id,
            "name": name,
            "args": args,
            "approved": False,
            "event": threading.Event(),
        }
        with WAITING_LOCK:
            WAITING[confirm_id] = record
        try:
            if not record["event"].wait(CONFIRM_TIMEOUT):
                return False  # 超时 = 拒绝
            return record["approved"]
        finally:
            with WAITING_LOCK:
                WAITING.pop(confirm_id, None)
 
    return confirm
class ConfirmIn(BaseModel):
    confirm_id: str
    approved: bool
# 前端轮询：当前有没有等着确认的工具
@app.get("/sessions/{session_id}/pending")
def get_pending(session_id: str):
    with WAITING_LOCK:
        for confirm_id, rec in WAITING.items():
            if rec["session_id"] == session_id:
                return {"pending": {"id": confirm_id, "name": rec["name"], "args": rec["args"]}}
    return {"pending": None}
# 前端点“是/否”后调用
@app.post("/sessions/{session_id}/confirm")
def confirm_tool(session_id: str, body: ConfirmIn):
    with WAITING_LOCK:
        rec = WAITING.get(body.confirm_id)
        if rec is None or rec["session_id"] != session_id:
            raise HTTPException(status_code=404, detail="没有待确认的工具调用（可能已超时）")
        rec["approved"] = body.approved
        rec["event"].set()
    return {"ok": True, "approved": body.approved}
#判断会话是否存在
def _check_session(session_id: str) -> None:
    if not store.exists(session_id):
        raise HTTPException(status_code=404, detail=f"会话不存在：{session_id}")
#创建新绘话
@app.post("/sessions")
def create_new_session(body:CreateSession):
     return {"id": store.create(body.title)}
#获取会话列表
@app.get("/sessions")
def list_sessions():
    return {"sessions": store.list()}
#获取具体会话窗口的消息
@app.get("/sessions/{session_id}/messages")
def get_messages(session_id:str):
    _check_session(session_id)
    return {"messages": store.load(session_id)}
#删除某个会话
@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    _check_session(session_id)
    store.delete(session_id)
    return {"deleted": session_id}
#agentchat接口
@app.post("/sessions/{session_id}/chat")
def chat(session_id:str,body:ChatIn):
    _check_session(session_id)
    text = body.message.strip()
    if not text:
        raise  HTTPException(status_code=400, detail="message 不能为空")
    messages = [{"role":"system","content":SYSTEM_PROMPT}]+store.load(session_id)
    agent = Agent(
        client,schemas,impls,trace = Trace(),messages = messages, confirm=make_confirm(session_id),
    )
    base = len(agent.messages)
    agent.chat(text)
    store.append(session_id, agent.messages[base:])
    return {"messages": agent.messages[1:]}

@app.post("/sessions/{session_id}/chat/stream")
def chat_stream(session_id: str, body: ChatIn):
    # 参数校验必须在返回 StreamingResponse 之前做完，
    # 因为一旦开始返回 200 + 流，就没法再改状态码了
    _check_session(session_id)
    text = body.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="message 不能为空")
 
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + store.load(session_id)
    agent = Agent(
        client, schemas, impls,
        trace=Trace(),
        messages=messages,
        confirm=make_confirm(session_id),  # 后端确认接口做好后换成 make_confirm(session_id)
    )
    base = len(agent.messages)
 
    def gen():
        try:
            # Agent.stream 自己会 yield token / tool_call / tool_result / done / error
            for event in agent.stream(text):
                yield _sse(event)
        except Exception as e:
            # 异常不能再改 HTTP 状态码（头已经发出去了），只能作为事件推给前端
            yield _sse({"type": "error", "message": f"{type(e).__name__}: {e}"})
        finally:
            # 正常结束 / 出错 / 客户端断开都会走这里，保证历史落库
            store.append(session_id, agent.messages[base:])
 
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 关掉 nginx 缓冲，否则会攒一堆再一次性吐出来
        },
    )