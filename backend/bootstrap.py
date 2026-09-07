"""全新运行环境初始化：建最新表结构并写入不含个人信息的区域字典。"""

from sqlmodel import Session, select

from models import Area, engine, init_db
from seed import AREAS


def bootstrap_database():
    init_db()
    with Session(engine) as session:
        existing_codes = set(session.exec(select(Area.code)).all())
        for code, name in AREAS:
            if code not in existing_codes:
                session.add(Area(code=code, name=name))
        session.commit()


if __name__ == "__main__":
    bootstrap_database()
    print("数据库初始化完成：表结构与游戏区域已就绪")
