"""MySQL 工具 - 与 Go 版 mysql_crud 对齐的可控数据库访问能力。"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.tools import tool
from loguru import logger

from app.config import config

WRITE_SQL_RE = re.compile(r"^\s*(insert|update|delete|replace|create|alter|drop|truncate)\b", re.I)


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


@tool
def mysql_crud(dsn: str, sql: str, operate_type: str = "query") -> str:
    """执行 MySQL SQL 并以 JSON 返回结果。

    默认仅允许 `query`/SELECT 类只读查询。写操作需要显式设置环境变量
    `MYSQL_CRUD_ALLOW_WRITE=True`，避免 Agent 在无人确认时修改数据库。

    Args:
        dsn: PyMySQL 兼容 DSN，例如 mysql://user:pass@127.0.0.1:3306/db?charset=utf8mb4
        sql: 要执行的 SQL。
        operate_type: query、insert、update 或 delete。
    """
    if not dsn.strip():
        return _json({"success": False, "message": "dsn is required"})
    if not sql.strip():
        return _json({"success": False, "message": "sql is required"})

    op = operate_type.lower().strip() or "query"
    is_write = op != "query" or bool(WRITE_SQL_RE.match(sql))
    if is_write and not config.mysql_crud_allow_write:
        return _json(
            {
                "success": False,
                "message": "写操作已被配置禁止。若确认需要执行，请设置 MYSQL_CRUD_ALLOW_WRITE=True。",
            }
        )

    try:
        import pymysql
        from pymysql.cursors import DictCursor
        from pymysql.err import MySQLError
        from pymysql.connections import Connection
        from urllib.parse import parse_qs, unquote, urlparse
    except ImportError:
        return _json(
            {
                "success": False,
                "message": "缺少可选依赖 pymysql，请先安装 PyMySQL 后再使用 mysql_crud 工具。",
            }
        )

    try:
        parsed = urlparse(dsn)
        if parsed.scheme not in {"mysql", "mysql+pymysql"}:
            return _json({"success": False, "message": "DSN scheme must be mysql or mysql+pymysql"})

        query = parse_qs(parsed.query)
        charset = query.get("charset", ["utf8mb4"])[0]
        port = parsed.port or 3306
        database = parsed.path.lstrip("/")

        conn: Connection = pymysql.connect(
            host=parsed.hostname or "127.0.0.1",
            port=port,
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            database=database or None,
            charset=charset,
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
        )
    except Exception as e:
        logger.warning("MySQL 连接失败: {}", e)
        return _json({"success": False, "message": f"connect failed: {e}"})

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                if op == "query" and not is_write:
                    rows = cursor.fetchall()
                    return _json(
                        {
                            "success": True,
                            "operate_type": op,
                            "row_count": len(rows),
                            "rows": rows,
                            "message": "query executed successfully",
                        }
                    )

                affected = cursor.rowcount
                conn.commit()
                return _json(
                    {
                        "success": True,
                        "operate_type": op,
                        "affected_rows": affected,
                        "message": "SQL executed successfully",
                    }
                )
    except MySQLError as e:
        conn.rollback()
        logger.warning("MySQL 执行失败: {}", e)
        return _json({"success": False, "message": f"SQL execution failed: {e}"})
