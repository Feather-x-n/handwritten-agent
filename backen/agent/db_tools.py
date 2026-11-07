import contextlib
import re
import sqlite3
import time
from pathlib import Path

from .file_tools import _safe_path
from .tools import tool

DATA_DIR = (Path(__file__).resolve().parents[1] / "workspace" / "data").resolve()
MAX_ROWS = 50
QUERY_TIMEOUT = 2.0
PROGRESS_STEPS = 10_000

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex|trigger)\b",
    re.I,
)


def _run_readonly(path: Path, sql: str) -> str:
    """在只读连接上执行 SQL，返回格式化文本。"""
    with contextlib.closing(
        sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    ) as conn:
        deadline = time.monotonic() + QUERY_TIMEOUT
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), PROGRESS_STEPS)
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS + 1)

    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]

    lines = [" | ".join(columns)]
    for row in rows:
        lines.append(" | ".join("" if v is None else str(v) for v in row))

    result = f"{len(rows)} 行\n" + "\n".join(lines)
    if truncated:
        result += f"\n（结果超过 {MAX_ROWS} 行，只显示前 {MAX_ROWS} 行）"
    return result


@tool
def query_db(sql: str, db: str = "company.db") -> str:
    """查询工作区 data/ 目录下的 SQLite 数据库，只允许 SELECT。
    现有表：employees(id, name, dept, title, hire_date, salary)、
    expenses(id, employee_id, amount, category, status, submit_date)。
    status 取值：已通过、已拒绝、待审批。用户问员工、部门、报销单等数据时使用。"""
    body = sql.strip().rstrip(";").strip()
    if not body:
        return "错误：SQL 为空"
    if ";" in body:
        return "错误：一次只能执行一条 SQL"
    if not re.match(r"^\s*(select|with)\b", body, re.I):
        return "错误：只允许 SELECT 查询"
    if _FORBIDDEN.search(body):
        return "错误：SQL 包含不允许的关键字"

    try:
        path = _safe_path(db, DATA_DIR)
    except ValueError as e:
        return f"错误：{e}"
    if not path.is_file():
        return f"错误：数据库 {db} 不存在"

    try:
        return _run_readonly(path, body)
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            return f"错误：查询超时（超过 {QUERY_TIMEOUT:g} 秒）"
        return f"错误：SQL 执行失败：{e}"
    except sqlite3.Error as e:
        return f"错误：SQL 执行失败：{e}"