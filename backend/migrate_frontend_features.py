"""园所归属与导出历史的幂等迁移；真实库备份由调用方在执行前完成。"""

import sqlite3

from sqlmodel import SQLModel

from config import DATABASE_PATH
from models import ExportRecord, engine  # noqa: F401

LEGACY_KINDERGARTEN_NAME = "待设置园所（历史数据）"


def migrate_frontend_feature_schema():
    with sqlite3.connect(DATABASE_PATH) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(classroom)")
        }
        if "kindergarten_id" not in columns:
            connection.execute(
                "ALTER TABLE classroom ADD COLUMN kindergarten_id INTEGER "
                "REFERENCES kindergartens(id)"
            )

        # 能由教师账号明确推出园所的班级才自动回填；冲突时拒绝猜测。
        conflicts = connection.execute(
            """
            SELECT teacher.classroom_id
            FROM teacher
            JOIN accounts ON accounts.teacher_id = teacher.id
            WHERE accounts.deleted_at IS NULL
            GROUP BY teacher.classroom_id
            HAVING COUNT(DISTINCT accounts.kindergarten_id) > 1
            """
        ).fetchall()
        if conflicts:
            raise RuntimeError(f"班级存在冲突的园所归属：{conflicts}")
        connection.execute(
            """
            UPDATE classroom
            SET kindergarten_id = (
                SELECT accounts.kindergarten_id
                FROM teacher
                JOIN accounts ON accounts.teacher_id = teacher.id
                WHERE teacher.classroom_id = classroom.id
                  AND accounts.deleted_at IS NULL
                LIMIT 1
            )
            WHERE kindergarten_id IS NULL
              AND EXISTS (
                SELECT 1
                FROM teacher
                JOIN accounts ON accounts.teacher_id = teacher.id
                WHERE teacher.classroom_id = classroom.id
                  AND accounts.deleted_at IS NULL
              )
            """
        )
        unassigned = connection.execute(
            "SELECT COUNT(*) FROM classroom WHERE kindergarten_id IS NULL"
        ).fetchone()[0]
        if unassigned:
            legacy = connection.execute(
                "SELECT id FROM kindergartens WHERE name = ? ORDER BY id LIMIT 1",
                (LEGACY_KINDERGARTEN_NAME,),
            ).fetchone()
            if legacy:
                legacy_id = legacy[0]
            else:
                cursor = connection.execute(
                    "INSERT INTO kindergartens (name, created_at) VALUES (?, CURRENT_TIMESTAMP)",
                    (LEGACY_KINDERGARTEN_NAME,),
                )
                legacy_id = cursor.lastrowid
            connection.execute(
                "UPDATE classroom SET kindergarten_id = ? WHERE kindergarten_id IS NULL",
                (legacy_id,),
            )
        connection.commit()

    SQLModel.metadata.create_all(engine, tables=[ExportRecord.__table__])


def verify_frontend_feature_schema():
    with sqlite3.connect(DATABASE_PATH) as connection:
        classroom_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(classroom)")
        }
        export_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='export_records'"
        ).fetchone()
        unassigned = connection.execute(
            "SELECT COUNT(*) FROM classroom WHERE kindergarten_id IS NULL"
        ).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if "kindergarten_id" not in classroom_columns:
        raise RuntimeError("classroom.kindergarten_id 创建失败")
    if not export_exists:
        raise RuntimeError("export_records 创建失败")
    if integrity != "ok":
        raise RuntimeError(f"数据库完整性检查失败：{integrity}")
    return unassigned


if __name__ == "__main__":
    migrate_frontend_feature_schema()
    unassigned_count = verify_frontend_feature_schema()
    print(f"前端功能表迁移完成；仍待归属的历史班级：{unassigned_count} 个")
