import httpx
from urllib.parse import urljoin, urlsplit
 
from .config import ALLOWED_HOSTS, HTTP_MAX_BYTES, HTTP_MAX_CHARS, HTTP_TIMEOUT
from .tools import SecurityError, tool
MAX_REDIRECTS = 3
ALLOWED_SCHEMES = {"https"}
ALLOWED_PORTS = {443}

#校验地址是否合法
def _check_url(url:str)->None:
    """校验 URL，不通过就抛 SecurityError。"""
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise SecurityError(f"不允许的 URL scheme: {parts.scheme}")
    if parts.username or parts.password:
        raise SecurityError("不允许在 URL 中包含用户名或密码")
    try:
        port = parts.port
    except ValueError:
        raise SecurityError(f"无效的 URL 端口")
    if port is not None and port not in ALLOWED_PORTS:
        raise SecurityError(f"不允许的 URL 端口: {port}")
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise SecurityError(f"不允许的 URL 主机: {host}")
#安全的读数据
def _read_limited(res:httpx.Response)->bytes:
    """从响应中读取数据，限制最大字节数和最大字符数。"""
    data = bytearray()
    for chunk in res.iter_bytes():
        data.extend(chunk)
        if len(data)> HTTP_MAX_BYTES:
            del data[HTTP_MAX_BYTES:]
            break
    return bytes(data)
#定义工具
@tool
def fetch_url(url:str)->str:
    """从指定 URL 获取内容，限制最大字节数和最大字符数。"""
    current_url = url.strip()
    try:
        #创建链接客户端容器
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=False, trust_env=False) as client:
            for _ in range(MAX_REDIRECTS+1):
                _check_url(current_url)
                #使用流式访问网页，防止数据过大
                with client.stream("GET",current_url) as res:
                    #如果网页重定向，获取 Location 头，继续访问
                    if res.is_redirect:
                        location = res.headers.get("Location")
                        if not location:
                            raise SecurityError(f"重定向响应缺少 Location 头")
                        current_url = urljoin(current_url, location)
                        continue
                    #获取状态码和内容类型
                    status = res.status_code
                    content_type = res.headers.get("Content-Type","")
                    #加载数据
                    body = _read_limited(res)
                    break
            else:
                raise SecurityError(f"重定向次数超过 {MAX_REDIRECTS} 次")
    except httpx.RequestError as e:
        return f"错误：请求失败: {e}"
    if content_type and not any(t in content_type for t in ("text", "json", "xml")):
        return f"错误：不允许的 Content-Type: {content_type}"
    #对数据进行解码
    text = body.decode("utf-8",errors="replace")
    if len(text)> HTTP_MAX_CHARS:
        text = text[:HTTP_MAX_CHARS] + f"\n（内容超过 {HTTP_MAX_CHARS} 字符，只显示前 {HTTP_MAX_CHARS} 字符）"
    return f"URL：{current_url}\n状态码：{status}\n类型：{content_type or '未知'}\n内容：\n{text}"

   