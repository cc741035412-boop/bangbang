"""账号与认证表的幂等迁移；数据库备份由调用方在运行本脚本前完成。"""

import sqlite3

from sqlmodel import SQLModel

from config import DATABASE_PATH
from models import Account, AuthSession, Kindergarten, SMSCode, engine  # noqa: F401


AUTH_TABLES = [
    Kindergarten.__table__,
    Account.__table__,
    SMSCode.__table__,
    AuthSession.__table__,
]


def migrate_auth_schema():
    SQLModel.metadata.create_all(engine, tables=AUTH_TABLES)


def verify_auth_schema():
    expected = {"kindergartens", "accounts", "sms_codes", "auth_sessions"}
    with sqlite3.connect(DATABASE_PATH) as connection:
        actual = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    missing = expected - actual
    if missing:
        raise RuntimeError(f"认证表创建失败：{sorted(missing)}")
    if integrity != "ok":
        raise RuntimeError(f"数据库完整性检查失败：{integrity}")
    return sorted(expected)


if __name__ == "__main__":
    migrate_auth_schema()
    tables = verify_auth_schema()
    print(f"认证表迁移完成：{'、'.join(tables)}")
