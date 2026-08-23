"""SQLite 就地迁移脚本，可重复运行，不删表、不重建数据库。"""

import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

from sqlmodel import SQLModel
from models import engine  # noqa: F401  导入 models 才能让 SQLModel 知道有哪些表

DB_FILE = Path("bangbang.db")
BACKUP_DIR = Path("backups")

# 要给 observation 表补的字段：(字段名, SQLite 类型)
# 全部允许为空，这样已有的那条测试数据不会报错
NEW_OBSERVATION_COLUMNS = [
    ("classroom_id",     "INTEGER"),
    ("purpose",          "TEXT"),
    ("narrative",        "TEXT"),
    ("narrative_source", "VARCHAR"),
    ("narrative_ai_raw", "TEXT"),
    ("analysis",         "TEXT"),
    ("strategy",         "TEXT"),
    ("created_at",       "DATETIME"),
    ("processing_started_at", "DATETIME"),
    ("ready_at",              "DATETIME"),
    ("confirmed_at",     "DATETIME"),
    ("failure_reason",        "TEXT"),
]


def backup_database():
    """任何结构或数据迁移前先创建带时间戳的数据库副本。"""
    if not DB_FILE.exists():
        print("⓪ 数据库尚不存在，无需备份")
        return None

    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_file = BACKUP_DIR / f"bangbang-{stamp}.db"
    shutil.copy2(DB_FILE, backup_file)
    print(f"⓪ 迁移前备份：{backup_file}")
    return backup_file


def observation_summary(label):
    """打印迁移前后记录数和状态分布。"""
    if not DB_FILE.exists():
        print(f"{label}：observation=0，状态分布={{}}")
        return

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    table_exists = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='observation'"
    ).fetchone()
    if not table_exists:
        conn.close()
        print(f"{label}：observation=0，状态分布={{}}")
        return

    count = cur.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
    distribution = dict(cur.execute(
        "SELECT status, COUNT(*) FROM observation GROUP BY status ORDER BY status"
    ).fetchall())
    conn.close()
    print(f"{label}：observation={count}，状态分布={distribution}")


def create_new_tables():
    """建出 models.py 里定义了、但数据库里还没有的表"""
    SQLModel.metadata.create_all(engine)
    print("① 新表已创建（已存在的表会自动跳过）")


def add_missing_columns():
    """给 observation 表补字段"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # 先看看现在已经有哪些字段
    existing = {row[1] for row in cur.execute("PRAGMA table_info(observation)")}

    added = []
    for col_name, col_type in NEW_OBSERVATION_COLUMNS:
        if col_name in existing:
            continue
        cur.execute(f"ALTER TABLE observation ADD COLUMN {col_name} {col_type}")
        added.append(col_name)

    conn.commit()
    conn.close()

    if added:
        print(f"② observation 表新增字段：{'、'.join(added)}")
    else:
        print("② observation 表字段已齐全，无需改动")


def migrate_status_values():
    """把旧状态映射到新状态；已迁移数据重复运行不会变化。"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "UPDATE observation SET status = 'ready_for_review' WHERE status = 'draft'"
    )
    migrated = cur.rowcount
    conn.commit()
    conn.close()
    print(f"③ 状态迁移：draft → ready_for_review，共 {migrated} 条")


def show_result():
    """把最终结果打出来，方便肉眼确认"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    print("\n===== 迁移后的数据库 =====")
    for (table,) in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ):
        count = cur.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        print(f"  {table:<18} {count} 行")

    print("\n===== observation 表字段 =====")
    for row in cur.execute("PRAGMA table_info(observation)"):
        print(f"  {row[1]}")

    conn.close()


if __name__ == "__main__":
    backup_database()
    observation_summary("迁移前")
    create_new_tables()
    add_missing_columns()
    migrate_status_values()
    observation_summary("迁移后")
    show_result()
    print("\n✅ 迁移完成：未删表、未重建数据库")
