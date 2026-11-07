from pathlib import Path
from .tools import tool
#定义agent的读写工具，提供白名单工作目录
WORKSPACE = (Path(__file__).resolve().parents[1] / "workspace").resolve()
REPORTS_DIR = WORKSPACE / "reports"
 
MAX_READ_BYTES = 100_000
MAX_WRITE_BYTES = 200_000
#解析相对路径
def _safe_path(relative:str,root:Path)->Path:
    """把相对路径解析到 root 内；越界就抛 ValueError。"""
    raw = Path(relative)
    if raw.is_absolute():
        raise ValueError("不允许绝对路径")
    if ".." in raw.parts:
        raise ValueError("不允许包含 ..")
 
    target = (root / raw).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("路径不在工作区内")
    return target
#读文件的工具
@tool
def read_file(path:str)->str:
    """读取工作区内的文本文件。path 是相对 workspace/ 的路径，例如 notes/a.md。"""
    try:
        target = _safe_path(path, WORKSPACE)
    except ValueError as e:
        return f"错误：{e}"
    if not target.is_file():
        return f"错误：{path} 文件不存在"
    if target.stat().st_size > MAX_READ_BYTES:
        return f"错误：{path} 文件过大，超过 {MAX_READ_BYTES} 字节"
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "错误：不是 UTF-8 文本文件"
#写文件的工具
@tool(confirm=True)
def write_file(filename:str, content:str)->str:
    """把报告写入工作区 reports/ 目录。filename 必须以 .md 结尾，例如 daily.md。"""
    if not filename.endswith(".md"):
        return "错误：文件名必须以 .md 结尾"
    data = content.encode("utf-8")
    if len(data) > MAX_WRITE_BYTES:
        return f"错误：内容超过 {MAX_WRITE_BYTES} 字节"
    try:
        target = _safe_path(filename, REPORTS_DIR)
    except ValueError as e:
        return f"错误：{e}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已写入 {target.relative_to(WORKSPACE)}（{len(data)} 字节）"