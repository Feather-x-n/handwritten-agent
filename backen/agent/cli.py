import sys
import json
from .llm import LLMClient
from .runtime import Agent
from .traces import Trace
from .tools import get_schemas, get_impls
from .config import SYSTEM_PROMPT
from .store import SessionStore
from . import rag_tools
from . import builtin_tools
from . import file_tools 
from . import db_tools
from . import web_tools
schemas = get_schemas()
impls = {**get_impls()}
trace = Trace()
client = LLMClient()
if __name__ == "__main__":
    store = SessionStore()
    session_id = sys.argv[1] if len(sys.argv) > 1 else None
    if session_id and not store.exists(session_id):
        print(f"会话不存在：{session_id}")
        sys.exit(1)
    if not session_id:
        session_id = store.create("终端会话")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + store.load(session_id)
    agent = Agent(client, schemas, impls, trace=trace, messages=messages)
    base = len(agent.messages)
    print(f"==== DeepSeek 对话助手（会话 {session_id}），输入 exit 退出 ====")
    if base > 1:
        print(f"已加载 {base - 1} 条历史消息")
    while True:
        user_text = input("\n你：")
        if user_text.strip().lower() == "exit":
            print("对话结束")
            break
        print("模型：", end="", flush=True)
        for event in agent.stream(user_text):
            if event["type"] == "token":
                print(event["text"], end="", flush=True)
            elif event["type"] == "tool_call":
                args = json.dumps(event["args"], ensure_ascii=False)
                print(f"\n  [调用] {event['name']} {args}", flush=True)
            elif event["type"] == "tool_result":
                text = str(event["result"]).replace("\n", " ")
                print(f"  [结果] {text[:100]}", flush=True)
            elif event["type"] == "error":
                print(f"\n  [错误] {event['message']}", flush=True)
        print()
        store.append(session_id, agent.messages[base:])
        base = len(agent.messages)
    print(f"会话已保存，下次续聊：python -m agent.cli {session_id}")