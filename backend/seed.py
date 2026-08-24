from sqlmodel import Session, select
from models import engine, Area, ClassRoom, Child, Teacher
from config import DEFAULT_TEACHER_NAME

# 8 个游戏区域
AREAS = [
    ("construction", "建构区"),
    ("sand_water",   "沙水区"),
    ("climbing",     "攀爬区"),
    ("roleplay",     "角色区"),
    ("art",          "美工区"),
    ("reading",      "阅读区"),
    ("science",      "科探区"),
    ("outdoor",      "户外综合"),
]

# 测试用的假名字（真实幼儿信息不进测试库，从第一天就养成这个习惯）
CHILDREN = ["王小满", "李念安", "周允之", "赵知夏", "孙朗月"]


def seed():
    with Session(engine) as session:

        # 防呆：已经塞过就不再塞，避免重复
        if session.exec(select(Area)).first():
            print("⚠️  数据已经塞过了，跳过")
            return

        # 1. 塞区域
        for code, name in AREAS:
            session.add(Area(code=code, name=name))

        # 2. 塞班级
        c = ClassRoom(name="中二班", age_group="middle")
        session.add(c)
        session.commit()        # 先存一次，数据库才会给这个班分配 id
        session.refresh(c)      # 把分配到的 id 读回来

        # 3. MVP 默认教师；接入登录后由账号决定当前教师
        session.add(Teacher(name=DEFAULT_TEACHER_NAME, classroom_id=c.id))

        # 4. 塞幼儿，挂到这个班下面
        for n in CHILDREN:
            session.add(Child(name=n, classroom_id=c.id))

        session.commit()        # 最后统一保存

    print("✅ 数据塞好了：8 个区域、1 个班、5 个小朋友")


if __name__ == "__main__":
    seed()
