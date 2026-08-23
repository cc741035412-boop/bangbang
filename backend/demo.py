"""
一键演示脚本：把整条闭环从头到尾跑一遍

用法（服务必须已经在另一个终端标签里跑着）：
    python demo.py

它会依次调用 9 个接口，每一步打印结果，最后给出 AI 候选采纳率。
不改任何代码，只是当一个"假的前端"来验证后端。
"""

import sys
import httpx

BASE = "http://127.0.0.1:8000"
LINE = "─" * 62


def step(n, title):
    print(f"\n{LINE}\n【第 {n} 步】{title}\n{LINE}")


def die(msg, resp=None):
    print(f"\n❌ {msg}")
    if resp is not None:
        print(f"   状态码 {resp.status_code}：{resp.text[:400]}")
    sys.exit(1)


def main():
    c = httpx.Client(base_url=BASE, timeout=30)

    # ---------- 0 服务是否活着 ----------
    try:
        r = c.get("/health")
    except Exception:
        die("连不上服务。请确认另一个终端标签里 uvicorn 正在运行。")
    if r.status_code != 200:
        die("服务没起来", r)
    print("✅ 服务正常")

    # ---------- 1 查基础数据 ----------
    step(1, "查班级里的小朋友和游戏区域")
    children = c.get("/children").json()
    areas = c.get("/areas").json()
    if not children or not areas:
        die("数据库里没有幼儿或区域，请先运行 python seed.py")

    child = children[0]
    area = next((a for a in areas if a["code"] == "construction"), areas[0])
    print(f"  观察对象：{child['name']}（id={child['id']}）")
    print(f"  游戏区域：{area['name']}（{area['code']}）")

    # ---------- 2 上传素材 ----------
    step(2, "上传一段模拟视频素材（35 分钟）")
    fake_video = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048   # 假的 mp4，只为演示
    r = c.post(
        "/uploads",
        files={"file": ("demo.mp4", fake_video, "video/mp4")},
        params={"duration_sec": 2100},
    )
    if r.status_code != 201:
        die("上传失败", r)
    media = r.json()
    print(f"  素材 id={media['id']}  文件名={media['stored_filename']}")
    print(f"  时长 {media['duration_sec']} 秒 —— 这个数字待会儿会被纯计算规则直接用上")

    # ---------- 3 建观察记录 ----------
    step(3, "新建一条观察记录草稿")
    r = c.post("/observations", json={
        "child_id": child["id"],
        "area_id": area["id"],
        "age_group": "middle",
        "media_type": "video",
        "purpose": "观察幼儿的搭建能力，了解其专注度与解决问题的能力",
    })
    if r.status_code != 201:
        die("创建观察记录失败", r)
    obs = r.json()
    obs_id = obs["id"]
    print(f"  观察记录 id={obs_id}，状态={obs['status']}")
    print(f"  班级已自动从幼儿身上带出：classroom_id={obs['classroom_id']}")

    # ---------- 4 绑定素材 ----------
    step(4, "把素材绑定到这条记录上")
    r = c.post(f"/observations/{obs_id}/attach-media", params={"media_id": media["id"]})
    if r.status_code != 200:
        die("绑定失败", r)
    print(f"  ✅ {r.json()}")

    # ---------- 5 AI 生成白描 ----------
    step(5, "【AI 工作流 A】生成客观白描")
    r = c.post(f"/observations/{obs_id}/narrative")
    if r.status_code != 200:
        die("生成白描失败", r)
    d = r.json()
    print(f"  {d['notice']}")
    print(f"\n  {d['narrative']}\n")

    # ---------- 6 AI 推荐候选指标 ----------
    step(6, "【AI 工作流 B】推荐候选指标")
    r = c.post(f"/observations/{obs_id}/suggest-tags")
    if r.status_code != 200:
        die("推荐指标失败", r)
    d = r.json()
    print(f"  {d['notice']}\n")

    for q in d["quant_hits"]:
        print(f"  🔢 系统判定（纯计算，零幻觉）")
        print(f"     {q['indicator_code']} {q['indicator_name']} · "
              f"{ {1:'初阶',2:'中阶',3:'高阶'}[q['level']] }")
        print(f"     依据：{q['basis']}\n")

    sugs = d["suggestions"]
    if not sugs:
        die("没有候选指标，无法继续演示")
    for s in sugs:
        lv = {1: "初阶", 2: "中阶", 3: "高阶"}[s["level"]]
        print(f"  🤖 AI 建议 #{s['rank']}  置信度 {s['confidence']}")
        print(f"     {s['indicator_code']} {s['indicator_name']} · {lv}")
        print(f"     {s['level_desc']}")
        print(f"     理由：{s['reason']}\n")

    # ---------- 7 教师处理候选 ----------
    step(7, "教师逐条处理：采纳第 1 个，否掉最后 1 个")
    first, last = sugs[0], sugs[-1]

    r = c.patch(f"/observations/{obs_id}/tags/{first['tag_id']}",
                json={"accepted": True})
    print(f"  ✅ 采纳 {first['indicator_code']} {first['indicator_name']}")

    if last["tag_id"] != first["tag_id"]:
        r = c.patch(f"/observations/{obs_id}/tags/{last['tag_id']}",
                    json={"accepted": False, "reject_reason": "白描里没有对应证据"})
        print(f"  ❌ 否掉 {last['indicator_code']} {last['indicator_name']}（理由：白描里没有对应证据）")

    # ---------- 8 教师补一个 AI 没想到的 ----------
    step(8, "教师自己补一个 AI 没想到的指标")
    r = c.post(f"/observations/{obs_id}/tags",
               json={"indicator_code": "1.4", "level": 3})
    if r.status_code != 201:
        die("补标签失败", r)
    print(f"  ➕ 教师补充 1.4 身体行为目的性 · 高阶（这条会计入「AI 漏检率」）")

    # ---------- 9 教师补分析和措施，然后定稿 ----------
    step(9, "教师补写分析与措施，然后定稿")
    c.patch(f"/observations/{obs_id}", json={
        "analysis": "幼儿能使用扇形积木拼合成圆形，体现出对图形组合的初步认知；"
                    "但向外扩展时仅重复圈数，对螺旋等复杂空间结构的理解尚浅。",
        "strategy": "投放曲线、螺旋形积木及绳子、软管等辅助材料，"
                    "引导幼儿观察生活中的螺旋结构（蚊香、海螺壳）并尝试临摹搭建。",
    })
    r = c.post(f"/observations/{obs_id}/confirm")
    if r.status_code != 200:
        die("定稿失败", r)
    print(f"  ✅ 已定稿，共 {r.json()['accepted_tag_count']} 条已采纳指标")

    # ---------- 成果 1：完整记录 ----------
    print(f"\n{LINE}\n【成果 1】一份完整的观察记录\n{LINE}")
    detail = c.get(f"/observations/{obs_id}").json()
    for k in ["状态", "观察对象", "班级", "年龄段", "观察地点", "观察目的"]:
        print(f"  {k}：{detail[k]}")
    print(f"\n  观察描述（{detail['白描来源']}）：\n    {detail['观察描述']}")
    print(f"\n  观察分析：\n    {detail['观察分析']}")
    print(f"\n  措施：\n    {detail['措施']}")
    print(f"\n  已采纳指标：")
    for t in detail["已采纳指标"]:
        print(f"    · {t['编号']} {t['名称']} · {t['层级']}　（{t['来源']}）")
        print(f"      {t['行为描述']}")

    # ---------- 成果 2：采纳率 ----------
    print(f"\n{LINE}\n【成果 2】AI 效果指标 —— 这是作品集里最值钱的数字\n{LINE}")
    m = c.get("/metrics/ai-quality").json()
    for k in ["AI建议总数", "教师已处理", "教师采纳", "采纳率", "教师自己补的", "漏检率"]:
        print(f"  {k}：{m[k]}")
    print(f"  分维度采纳率：{m['分维度采纳率']}")
    print(f"\n  {m['说明']}")

    print(f"\n{LINE}\n🎉 全链路跑通了\n{LINE}\n")
    c.close()


if __name__ == "__main__":
    main()
