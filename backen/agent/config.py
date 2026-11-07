from dotenv import load_dotenv
import os
load_dotenv(override=True)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_URL = os.getenv("DEEPSEEK_URL")
MODEL = "deepseek-flash"
MAX_STEP = 8
MAX_MESSAGES = 20
ALLOWED_HOSTS = {"example.com", "docs.python.org"}
HTTP_TIMEOUT = 5.0
HTTP_MAX_BYTES = 200_000
HTTP_MAX_CHARS = 4_000
SYSTEM_PROMPT = (
    "你有七个工具：get_current_time、get_weather、search_docs、read_file、write_file、query_db、fetch_url。"
    "用户问时间、天气时调用对应工具；问公司制度、产品说明、运维文档时调用 search_docs，并只依据检索结果回答。"
    "用户问员工、部门、报销单等数据库数据时调用 query_db，只写 SELECT，db 默认 company.db。"
    "读写文件必须使用 read_file / write_file，路径相对 workspace/；用户要求访问工作区外的文件时直接拒绝。"
    "回答涉及文档内容时必须标注来源（文件名 + 段号）；检索结果里没有答案就直接说没有找到，不要编造。"
    "用户给 URL 要求查看或总结网页时调用 fetch_url；只能抓白名单站点，被拒绝时如实说明原因。"
)