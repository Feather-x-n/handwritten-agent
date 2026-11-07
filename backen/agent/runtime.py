import json
from .tools import SecurityError
from .config import MAX_MESSAGES, MAX_STEP, SYSTEM_PROMPT
from .llm import LLMClient
from .memory import trim
from .traces import Trace
class Agent:
   #初始化agent
    def __init__(self,client:LLMClient,TOOLS_SCHEMAS,TOOL_IMPLES,trace: Trace | None = None,
                 messages: list | None = None, confirm=None):
        self.messages = messages if messages is not None else [{
                "role":"system",
                "content":SYSTEM_PROMPT
            }]
        self.client = client
        self.trace = trace
        self.TOOLS_SCHEMAS = TOOLS_SCHEMAS
        self.TOOL_IMPLES = TOOL_IMPLES
        self.confirm = confirm
    #运行敏感工具时手动确认
    def _confirm(self,name:str,args:dict)->bool:
        if self.confirm is not None:
            approved = bool(self.confirm(name, args))
        else:
            preview = json.dumps(args,ensure_ascii=False)
            if len(preview) > 200:
                preview = preview[:200] + "..."
            try:
                answer = input(f"\n[确认] 要执行 {name} 吗？参数：{preview}\n输入 y 确认，其他取消：")
            except EOFError:
                answer = ""
            approved = answer.strip().lower() == "y"
        if self.trace:
            self.trace.log({"kind":"confirm","tool":name,"args":args,"approved":approved})
        return approved
    def run_tools(self,name:str,args:dict)->str:
        #获取工具映射
        func = self.TOOL_IMPLES.get(name)
        #判断工具是否存在
        if func is None:
            return f"错误：未知工具 {name}"
        #判断工具是否需要确认
        if getattr(func, "requires_confirm", False) and not self._confirm(name, args):
            return "错误：用户拒绝执行该操作"
        #执行工具
        try:
            return str(func(**args))
        except SecurityError as e:
            if self.trace:
                #记录工具日志
                self.trace.log({"kind":"security","tool":name,"args":args,"reason":str(e)})
            return f"错误：{e}"
        except Exception as e:
            return f"错误：{type(e).__name__}: {e}"
    # 模型对话逻辑
    # def chat(self,text:str)->str:
    #     self.messages.append({"role":"user","content":text})
    #     if self.trace:
    #         self.trace.log({"kind":"user","text":text})
    #     #倘若使用工具一直循环调用到tools_call为空，或者超过最大步数MAX_STEP，结束循环
    #     for step in range(1,MAX_STEP+1):
    #         #截取消息，限制最大消息数
    #         outgoing = trim(self.messages, MAX_MESSAGES)
    #         if self.trace and len(outgoing) != len(self.messages):
    #             self.trace.log({"kind": "trim", "before": len(self.messages), "after": len(outgoing)})
    #         #调用模型
    #         response = self.client.complete(outgoing,self.TOOLS_SCHEMAS,self.trace)
    #         #判断模型是否调用工具
    #         if not response.choices[0].message.tool_calls:
    #             self.messages.append({"role":"assistant","content":response.choices[0].message.content})
    #             if self.trace:
    #                 self.trace.log({"kind":"assistant_answer","text":response.choices[0].message.content,"tokens":response.usage.total_tokens})
    #             return response.choices[0].message.content
    #         if self.trace:
    #             self.trace.log({"kind":"assistant_tool_call","tool_calls":[{"name":tc.function.name,"args":tc.function.arguments} for tc in response.choices[0].message.tool_calls],"tokens":response.usage.total_tokens,"step":step})
    #         tc_msg = response.choices[0].message.tool_calls
    #         tools_msg = {"role":"assistant","content":""}
    #         tools_msg["tool_calls"] =[
    #             {
    #                 "id":tc.id,
    #                 "type": "function",
    #                 "function": {
    #                     "name": tc.function.name,
    #                     "arguments": tc.function.arguments,
    #                     },
    #             }
    #             for tc in tc_msg
    #         ]
    #         self.messages.append(tools_msg)
    #         #封装toolmessages
    #         for tc in tc_msg:
    #             name = tc.function.name 
    #             try:
    #                 args = json.loads(tc.function.arguments or "{}")
    #             except json.JSONDecodeError:
    #                 args, result = {}, "错误：参数不是合法 JSON"
    #             else:
    #                 result = self.run_tools(name, args)
    #             # try:
    #             #     args = json.loads(tc.function.arguments or "{}")
    #             #     result = self.run_tools(name, args)
    #             # except json.JSONDecodeError:
    #             #     result = "错误：参数不是合法 JSON"
    #             self.messages.append({"role":"tool","tool_call_id": tc.id,"content":result})
    #             if self.trace:
    #                 self.trace.log({"kind":"tool","name":name,"args":args,"result":result})
    #模型的流式调用
    def stream(self,text:str):
        self.messages.append({"role":"user","content":text})
        if self.trace:
            self.trace.log({"kind":"user","text":text})
        for step in range(1,MAX_STEP+1):
            outgoing = trim(self.messages,MAX_MESSAGES)
            if self.trace and len(outgoing) != len(self.messages):
                 self.trace.log({"kind": "trim", "before": len(self.messages), "after": len(outgoing)})
            content_parts = []
            tool_slots = {}
            usage = None
            try:
                for chunk in self.client.stream(outgoing,self.TOOLS_SCHEMAS,self.trace):
                    if getattr(chunk,"usage",None):
                        usage = chunk.usage
                    if not chunk.choices:          # usage 那个 chunk 没有 choices
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        content_parts.append(delta.content)
                        yield {"type": "token", "text": delta.content}
                   # 遍历当前增量里的工具调用分片，如果delta.tool_calls是None就当成空列表
                    for tc in (delta.tool_calls or []):
                        # setdefault：如果该index对应的槽位不存在，就新建一个初始字典；存在则直接取出已有slot
                        # 同一个工具调用会被拆成多个流分片，用index作为编号把分片拼到同一个slot里
                        slot = tool_slots.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                        # 如果分片里带了tool_call的id，更新slot的id（一般第一个分片会返回id）
                        if tc.id:
                            slot["id"] = tc.id
                        # 判断当前分片有没有function信息（函数名+参数）
                        if tc.function:
                            # 拿到函数名称，赋值（一般第一个分片就给出名字，后面分片不会再带name）
                            if tc.function.name:
                                slot["name"] = tc.function.name
                            # arguments是json字符串分片，是分段流出来的，不能覆盖，要不断拼接追加
                            if tc.function.arguments:
                                slot["arguments"] += tc.function.arguments
            except Exception as e:
                yield {"type": "error", "message": f"{type(e).__name__}: {e}"}
                return
 
            tokens = getattr(usage, "total_tokens", None)
            if not tool_slots:
                answer = "".join(content_parts)
                self.messages.append({"role": "assistant", "content": answer})
                if self.trace:
                    self.trace.log({"kind": "assistant_answer", "text": answer, "tokens": tokens})
                yield {"type": "done", "text": answer, "tokens": tokens}
                return
            tool_calls = [
                {
                    "id": slot["id"],
                    "type": "function",
                    "function": {"name": slot["name"], "arguments": slot["arguments"]},
                }
                for _, slot in sorted(tool_slots.items())
            ]
            self.messages.append({"role": "assistant", "content": "".join(content_parts), "tool_calls": tool_calls})
            if self.trace:
                self.trace.log({
                    "kind": "assistant_tool_call",
                    "tool_calls": [{"name": tc["function"]["name"], "args": tc["function"]["arguments"]} for tc in tool_calls],
                    "tokens": tokens,
                    "step": step,
                })
 
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args, result = {}, "错误：参数不是合法 JSON"
                else:
                    yield {"type": "tool_call", "name": name, "args": args, "id": tc["id"]}
                    result = self.run_tools(name, args)
                self.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                if self.trace:
                    self.trace.log({"kind": "tool", "name": name, "args": args, "result": result})
                yield {"type": "tool_result", "name": name, "result": result}
 
        # 跑满步数也要给调用方一个明确结果，不能静默返回 None
        yield {"type": "error", "message": f"超过最大步数 {MAX_STEP}，已停止"}
    def chat(self, text: str) -> str:
        answer = ""
        for event in self.stream(text):
            if event["type"] == "done":
                answer = event["text"]
            elif event["type"] == "error":
                answer = f"错误：{event['message']}"
        return answer