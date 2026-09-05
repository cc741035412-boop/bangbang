"""观察记录检索的幂等迁移：为 observation.observed_at 建立检索索引。

背景：GET /observations 支持按观察日期区间（date_from / date_to）过滤后，
过滤条件会落在 observation.observed_at 上。新库由 models 建表时自动带索引
（ix_observation_observed_at）；本脚本只负责把“已经存在、建表时没有索引”的
老库补上同一条索引，重复执行是安全的（CREATE INDEX IF NOT EXISTS）。

真实库备份由调用方在执行前完成；本脚本默认只读当前 DATABASE_PATH 指向的库。
"""

import sqlite3

from config import DATABASE_PATH

INDEX_NAME = "ix_observation_observed_at"
CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS ix_observation_observed_at "
    "ON observation (observed_at)"
)


def migrate_observation_search_index():
    """幂等补索引；显式事务保证要么建好、要么整体回滚。"""
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(CREATE_INDEX_SQL)
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def verify_observation_search_index() -> bool:
    with sqlite3.connect(DATABASE_PATH) as connection:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
            (INDEX_NAME,),
        ).fetchone()
    if not row:
        raise RuntimeError(f"索引 {INDEX_NAME} 创建失败")
    return True


if __name__ == "__main__":
    migrate_observation_search_index()
    verify_observation_search_index()
    print(f"✅ 索引 {INDEX_NAME} 已就绪（observation.observed_at）")
