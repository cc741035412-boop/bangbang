"""迁移脚本回归测试：对“无检索索引”的临时库跑迁移，验证建索引且幂等。

铁律：只允许对临时数据库执行写操作；本测试完全使用 tmp_path 下的临时库，
绝不触碰 backend/bangbang.db。迁移脚本通过子进程运行，环境变量 BANGBANG_DB_PATH
指向临时库，与真实库完全隔离。
"""

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
MIGRATE_SCRIPT = BACKEND_DIR / "migrate_observation_search.py"
INDEX_NAME = "ix_observation_observed_at"


def build_pre_migration_db(path: Path):
    """按“迁移前”的 schema 建最小临时库：observation 表存在但没有检索索引。"""
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE observation ("
        " id INTEGER PRIMARY KEY,"
        " child_id INTEGER, area_id INTEGER, classroom_id INTEGER,"
        " observer_id INTEGER, observed_at VARCHAR, age_group VARCHAR,"
        " status VARCHAR, created_at VARCHAR"
        ")"
    )
    cur.execute(
        "INSERT INTO observation (id, area_id, age_group, observed_at, status)"
        " VALUES (1, 1, 'middle', '2026-09-01T00:00:00Z', 'confirmed')"
    )
    conn.commit()
    conn.close()


def run_migrate(db_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["BANGBANG_DB_PATH"] = str(db_path)
    env["BANGBANG_AI_MODE"] = "mock"
    return subprocess.run(
        [sys.executable, str(MIGRATE_SCRIPT)],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def has_index(db: Path) -> bool:
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
            (INDEX_NAME,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


class MigrateObservationSearchIndexTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "fixture.db"
        build_pre_migration_db(self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def test_migration_creates_index_and_is_idempotent(self):
        self.assertFalse(has_index(self.db), "预迁移库不应已有索引")

        first = run_migrate(self.db)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(has_index(self.db), "迁移后索引应存在")

        # 重复执行不报错、不重复建
        second = run_migrate(self.db)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(has_index(self.db))

    def test_verify_fails_when_index_missing(self):
        # 验证函数独立可测：临时库没有索引时应当抛出错误
        env = dict(os.environ)
        env["BANGBANG_DB_PATH"] = str(self.db)
        env["BANGBANG_AI_MODE"] = "mock"
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import migrate_observation_search as m;"
                " m.verify_observation_search_index()",
            ],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(INDEX_NAME, result.stderr)


if __name__ == "__main__":
    unittest.main()
