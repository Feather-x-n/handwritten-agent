import os
from rich import print as rprint
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv(override=True)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_URL")

LLM_MODEL = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)
#创建会话
content = []
def chat(messages:str)->str:
    content.append({"role":"user","content":messages})
    response = LLM_MODEL.chat.completions.create(
    model="deepseek-flash",
    messages=content,
    stream=False,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
    if response.choices[0].message.role in ["assistan","user"]:
        content.append({"role":response.choices[0].message.role,"content":response.choices[0].message.content})
    return response.choices[0].message.content
if __name__ == "__main__":
    print("==== DeepSeek 对话助手，输入 exit 退出 ====")
    while True:
        user_text = input("\n你：")
        if user_text.strip().lower() == "exit":
            print("对话结束")
            break
        res = chat(user_text)
        print(f"模型：{res}")
