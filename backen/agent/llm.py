from openai import OpenAI
from . import config
from .traces import Trace
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
    BadRequestError,
    AuthenticationError
)
import time
class LLMClient:
    #初始化LLM
    def __init__(self):
        self.client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_URL
        )
        self.model = config.MODEL
    def complete(self, messages: list, tools, trace: Trace | None = None):
        retry_exceptions = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
        no_retry_exceptions = (BadRequestError, AuthenticationError)
        #应对网络异常和请求限制，最多重试5次，指数退避
        for attempt in range(1, 6):
            try:
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                )
            except no_retry_exceptions:
                raise
            except retry_exceptions as e:
                if trace is not None:
                    trace.log({"kind": "retry", "attempt": attempt, "error": type(e).__name__})
                if attempt == 5:
                    raise
                time.sleep(2 ** (attempt - 1))
    def stream(self,messages:list,tools,trace:Trace|None = None):
        retry_exceptions = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
        no_retry_exceptions = (BadRequestError, AuthenticationError)
        for attempt in range(1, 6):
            try:
                response = self.client.chat.completions.create(
                    model = self.model,
                    messages=messages,
                    tools = tools,
                    stream=True,
                    stream_options={"include_usage": True},   # 让最后一个 chunk 带 usage
                )
                first  = next(response)
            except no_retry_exceptions:
                raise
            except StopIteration:
                return
            except retry_exceptions as e:
                if trace is not None:
                    trace.log({"kind": "retry", "attempt": attempt, "error": type(e).__name__})
                if attempt == 5:
                    raise
                time.sleep(2 ** (attempt - 1))
                continue
            yield first
            for chunk in response:               # 这里再失败就不能重试了，否则用户会看到重复文字
                yield chunk
            return