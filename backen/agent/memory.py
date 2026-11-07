def trim(messages:list,max_messages:int = 20)->list:
    if len(messages) <= max_messages:
        return messages
 
    system = messages[0]                 # system 永远保留
    tail = messages[-(max_messages - 1):]
 
    # 起点不能是 tool：它前面的 assistant.tool_calls 已经被裁掉了，留着会 400
    while tail and tail[0].get("role") == "tool":
        tail = tail[1:]

    if not tail:
        tail = [m for m in messages if m.get("role") == "user"][-1:]

    return [system] + tail