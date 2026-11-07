from backen.agent.config import SYSTEM_PROMPT
from backen.agent.llm import LLMClient
from backen.agent.runtime import Agent
from backen.agent.store import SessionStore
from backen.agent.tools import get_schemas, get_impls
from backen.agent.traces import Trace

store = SessionStore()
sid = store.create("Day1 验证")
history = [{"role": "system", "content": SYSTEM_PROMPT}] + store.load(sid)
agent = Agent(LLMClient(), get_schemas(), get_impls(),
              trace=Trace(), messages=history, confirm=lambda name, args: False)

for text in ["北京现在几点？", "那纽约呢？"]:
    base = len(agent.messages)
    content = agent.chat(text)
    print(content)
    store.append(sid, agent.messages[base:])

# 重新加载，模拟服务重启
history2 = [{"role": "system", "content": SYSTEM_PROMPT}] + store.load(sid)
agent2 = Agent(LLMClient(), get_schemas(), get_impls(),
               trace=Trace(), messages=history2, confirm=lambda name, args: False)
content2 = agent2.chat("我刚才问的是哪两个城市？")   # 应该能答出北京和纽约
print(content)