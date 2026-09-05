"""迁移脚本回归测试：对"迁移前 schema"的临时库跑迁移，验证结果正确且幂等。

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
MIGRATE_SCRIPT = BACKEND_DIR / "migrate_frontend_features.py"


def build_pre_migration_db(path: Path):
    """按"迁移前"的 schema 建一个最小临时库，包含迁移脚本要读的表。

    迁移脚本只依赖 classroom / teacher / accounts / kindergartens 四张表：
    - classroom 没有 kindergarten_id（这就是要补的列）；
    - 没有账号可推导园所时，脚本应自动创建兜底园所并回填。
    """
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE classroom (id INTEGER PRIMARY KEY, name VARCHAR, age_group VARCHAR)"
    )
    cur.execute("INSERT INTO classroom (id, name, age_group) VALUES (1, '中二班', 'middle')")
    cur.execute(
        "CREATE TABLE teacher (id INTEGER PRIMARY KEY, name VARCHAR, classroom_id INTEGER)"
    )
    cur.execute("INSERT INTO teacher (id, name, classroom_id) VALUES (1, '蔡老师', 1)")
    cur.execute(
        "CREATE TABLE accounts (id INTEGER PRIMARY KEY, phone VARCHAR, "
        "teacher_id INTEGER, kindergarten_id INTEGER, role VARCHAR, created_at VARCHAR, "
        "deleted_at VARCHAR)"
    )
    cur.execute(
        "CREATE TABLE kindergartens (id INTEGER PRIMARY KEY, name VARCHAR, created_at VARCHAR)"
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


class MigrateFrontendFeaturesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "fixture.db"
        build_pre_migration_db(self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def assert_migrated(self, db: Path):
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        try:
            columns = {row[1] for row in cur.execute("PRAGMA table_info(classroom)")}
            self.assertIn("kindergarten_id", columns, "classroom.kindergarten_id 未创建")
            null_count = cur.execute(
                "SELECT COUNT(*) FROM classroom WHERE kindergarten_id IS NULL"
            ).fetchone()[0]
            self.assertEqual(null_count, 0, "存在未回填园所的班级")
            export_exists = cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='export_records'"
            ).fetchone()
            self.assertTrue(export_exists, "export_records 未创建")
            legacy = cur.execute(
                "SELECT id, name FROM kindergartens ORDER BY id"
            ).fetchall()
            self.assertTrue(legacy, "兜底园所未创建")
            self.assertEqual(cur.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(cur.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            conn.close()

    def test_migration_succeeds_and_backfills(self):
        result = run_migrate(self.db)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("仍待归属的历史班级：0 个", result.stdout)
        self.assert_migrated(self.db)
        # 回填的必须是兜底园所本身（账号表为空时不允许猜别的）
        conn = sqlite3.connect(self.db)
        try:
            row = conn.execute(
                "SELECT kindergarten_id FROM classroom WHERE id = 1"
            ).fetchone()
            kg_name = conn.execute(
                "SELECT name FROM kindergartens WHERE id = ?", (row[0],)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(kg_name, "待设置园所（历史数据）")

    def test_migration_is_idempotent(self):
        first = run_migrate(self.db)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = run_migrate(self.db)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        conn = sqlite3.connect(self.db)
        try:
            kindergartens = conn.execute("SELECT COUNT(*) FROM kindergartens").fetchone()[0]
            classrooms = conn.execute("SELECT COUNT(*) FROM classroom").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(kindergartens, 1, "幂等重跑不应重复创建兜底园所")
        self.assertEqual(classrooms, 1, "幂等重跑不应改变班级数据")

    def test_export_records_schema_matches_model(self):
        result = run_migrate(self.db)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        conn = sqlite3.connect(self.db)
        try:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(export_records)")]
        finally:
            conn.close()
        expected = {
            "id", "account_id", "observation_id", "scope", "format",
            "file_name", "size", "child_name", "storage_key", "created_at",
        }
        self.assertEqual(set(columns), expected)

    def test_conflicting_kindergarten_assignments_are_rejected_and_rolled_back(self):
        """同一班级被账号指向两个园所时，迁移必须拒绝猜测，且事务整体回滚。

        安全分支：宁可失败也不把班级随便塞进某一个园所（同名园所误并会
        让两个园互相看到对方的幼儿数据）。
        """
        conn = sqlite3.connect(self.db)
        cur = conn.cursor()
        cur.execute("INSERT INTO kindergartens (id, name) VALUES (1, '园所A'), (2, '园所B')")
        cur.execute(
            "INSERT INTO accounts (id, phone, teacher_id, kindergarten_id, role) "
            "VALUES (1, '13800000001', 1, 1, 'owner'), (2, '13800000002', 1, 2, 'owner')"
        )
        conn.commit()
        conn.close()

        result = run_migrate(self.db)
        self.assertNotEqual(result.returncode, 0, "冲突场景应当迁移失败")
        self.assertIn("冲突", result.stdout + result.stderr)

        # 失败后应保持原状：列未加、兜底园所未建、export_records 未建（事务回滚）
        conn = sqlite3.connect(self.db)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(classroom)")}
            self.assertNotIn("kindergarten_id", columns, "冲突失败后不应残留新列")
            self.assertFalse(
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='export_records'"
                ).fetchone(),
                "冲突失败后不应残留 export_records",
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
