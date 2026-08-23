"""SQLite 就地迁移脚本，可重复运行；结构变更前自动备份数据库。"""

import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

from sqlmodel import SQLModel
from config import DATABASE_PATH
from models import engine  # noqa: F401  导入 models 才能让 SQLModel 知道有哪些表

DB_FILE = DATABASE_PATH
BACKUP_DIR = Path("backups")

# 要给 observation 表补的字段：(字段名, SQLite 类型)
# 全部允许为空，这样已有的那条测试数据不会报错
NEW_OBSERVATION_COLUMNS = [
    ("classroom_id",     "INTEGER"),
    ("purpose",          "TEXT"),
    ("note",             "TEXT"),
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

NEW_OBSERVATIONTAG_COLUMNS = [
    ("ai_run_id", "INTEGER REFERENCES ai_run(id)"),
]

NEW_AI_RUN_COLUMNS = [
    ("temperature", "FLOAT"),
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


def add_missing_observationtag_columns():
    """给 observationtag 表补充与 AI 调用记录的可空关联。"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    existing = {row[1] for row in cur.execute("PRAGMA table_info(observationtag)")}

    added = []
    for col_name, col_type in NEW_OBSERVATIONTAG_COLUMNS:
        if col_name in existing:
            continue
        cur.execute(f"ALTER TABLE observationtag ADD COLUMN {col_name} {col_type}")
        added.append(col_name)

    conn.commit()
    conn.close()

    if added:
        print(f"③ observationtag 表新增字段：{'、'.join(added)}")
    else:
        print("③ observationtag 表字段已齐全，无需改动")


def add_missing_ai_run_columns():
    """给 AI 调用审计表补充后续实验参数。"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    existing = {row[1] for row in cur.execute("PRAGMA table_info(ai_run)")}

    added = []
    for col_name, col_type in NEW_AI_RUN_COLUMNS:
        if col_name in existing:
            continue
        cur.execute(f"ALTER TABLE ai_run ADD COLUMN {col_name} {col_type}")
        added.append(col_name)

    conn.commit()
    conn.close()

    if added:
        print(f"④ ai_run 表新增字段：{'、'.join(added)}")
    else:
        print("④ ai_run 表字段已齐全，无需改动")


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
    print(f"⑤ 状态迁移：draft → ready_for_review，共 {migrated} 条")


def rebuild_observation_for_quick_capture():
    """重建 observation，使 child_id、media_type 可空并保留全部原始数据。"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    columns = {row[1]: row for row in cur.execute("PRAGMA table_info(observation)")}
    already_migrated = (
        "note" in columns
        and columns["child_id"][3] == 0
        and columns["media_type"][3] == 0
    )
    if already_migrated:
        conn.close()
        print("⑥ observation 可空约束已符合现场沉淀模型，无需重建")
        return

    column_names = [
        "id", "child_id", "area_id", "observed_at", "age_group", "media_type",
        "status", "classroom_id", "purpose", "note", "narrative",
        "narrative_source", "narrative_ai_raw", "analysis", "strategy",
        "created_at", "confirmed_at", "processing_started_at", "ready_at",
        "failure_reason",
    ]

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("""
            CREATE TABLE observation_new (
                id INTEGER NOT NULL PRIMARY KEY,
                child_id INTEGER,
                area_id INTEGER NOT NULL,
                observed_at DATETIME NOT NULL,
                age_group VARCHAR NOT NULL,
                media_type VARCHAR,
                status VARCHAR NOT NULL,
                classroom_id INTEGER,
                purpose TEXT,
                note TEXT,
                narrative TEXT,
                narrative_source VARCHAR,
                narrative_ai_raw TEXT,
                analysis TEXT,
                strategy TEXT,
                created_at DATETIME,
                confirmed_at DATETIME,
                processing_started_at DATETIME,
                ready_at DATETIME,
                failure_reason TEXT,
                FOREIGN KEY(child_id) REFERENCES child(id),
                FOREIGN KEY(area_id) REFERENCES area(id),
                FOREIGN KEY(classroom_id) REFERENCES classroom(id)
            )
        """)
        joined = ", ".join(column_names)
        cur.execute(
            f"INSERT INTO observation_new ({joined}) "
            f"SELECT {joined} FROM observation"
        )
        cur.execute("DROP TABLE observation")
        cur.execute("ALTER TABLE observation_new RENAME TO observation")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

    foreign_key_errors = cur.execute("PRAGMA foreign_key_check").fetchall()
    conn.close()
    if foreign_key_errors:
        raise RuntimeError(f"迁移后外键检查失败：{foreign_key_errors}")
    print("⑥ observation 已重建：child_id、media_type 改为可空，原数据已复制")


def show_result():
    """把最终结果打出来，方便肉眼确认"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    print("\n===== 迁移后的数据库 =====")
    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    for (table,) in tables:
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
    add_missing_observationtag_columns()
    add_missing_ai_run_columns()
    migrate_status_values()
    rebuild_observation_for_quick_capture()
    observation_summary("迁移后")
    show_result()
    print("\n✅ 迁移完成：ai_run 与 observationtag.ai_run_id 已按需创建")
