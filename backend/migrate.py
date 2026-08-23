"""
一次性迁移脚本：
1. 新建 media、observationtag 两张新表
2. 给已存在的 observation 表补上新字段（不动已有数据）

可以重复运行，已经加过的字段会自动跳过。
"""

import sqlite3
from sqlmodel import SQLModel
from models import engine  # noqa: F401  导入 models 才能让 SQLModel 知道有哪些表

DB_FILE = "bangbang.db"

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
    ("confirmed_at",     "DATETIME"),
]


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
    create_new_tables()
    add_missing_columns()
    show_result()
    print("\n✅ 迁移完成，原有数据一条没动")
