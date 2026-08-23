"""
AI 服务层

【重要】当前是 DEMO MOCK，没有调用任何真实大模型。
所有 mock 输出都带 is_mock=True 标记，前端和演示时必须显示出来。

以后接真实 AI（Dify / 大模型 API）时，只需要替换这个文件里两个函数的内部实现，
main.py 一行都不用改。接口契约在下面的 docstring 里写死了。
"""

import re
from typing import List, Dict, Optional

from indicators import INDICATORS, AREA_PRIOR, DEFAULT_PRIOR


# ============================================================
# 工作流 A：素材 → 客观白描
# ============================================================

# DEMO 用的白描样本，按区域给不同文本，让演示看起来有区分度
# 全部遵守「纯客观白描」规则：只写看得见的动作、材料、语言、时长
# 禁止出现：认真、专注、聪明、良好、较弱、有进步 等评价性词汇
_MOCK_NARRATIVES = {
    "construction": (
        "幼儿A坐在地垫上，先从积木柜取来 4 块扇形积木，将它们首尾相接拼成一个圆形。"
        "拼好后，他把长条积木一块一块竖起来，沿着圆形外侧摆放，绕了一圈。"
        "第二圈摆到一半时有两块积木倒下，他把倒下的积木重新扶起，调整了间距后继续摆放。"
        "过程中幼儿B走近，幼儿A说“你搭那边”，幼儿B从另一侧开始摆放积木。"
    ),
    "sand_water": (
        "幼儿A用铲子将沙子铲进红色水桶，装到大半桶后双手抱起水桶，走到三步外的位置倾倒。"
        "倒完后他蹲下用手掌拍打沙堆表面，又用食指在沙面上划出一条沟。"
        "接着他把水壶里的水沿着沟倒下去，水流到一半处停住，他用手把沟挖深，水继续向前流。"
    ),
    "outdoor": (
        "活动开始时，多名幼儿各自手持大球，有的将球举过头顶抛出，有的追着滚动的球跑。"
        "教师叫停后，幼儿围坐成一圈，教师与幼儿依次发言，共同说出四条规则：只用一个球、"
        "只能用脚踢不能用手扔、踢球力气不能太大、不能超线。"
        "游戏重新开始后，幼儿分成两组分别站在场地两侧，交替把球踢向对面。"
        "过程中一名幼儿踢球后，另一名幼儿指着他说“力气太大啦，轻一点”；"
        "另一名幼儿跨到线外时，旁边幼儿拉他后退并说“不能超线”。"
    ),
    "roleplay": (
        "幼儿A把三块积木首尾相接放在地上，坐在最前面一块上，双手向前伸直做推的动作。"
        "他对走过来的教师说“地铁要出发了，你要去哪里”。教师回答后，他说“好，那上车吧”，"
        "并拍了拍身后的积木。幼儿B随后坐到后面一块积木上。"
    ),
}

_MOCK_DEFAULT_NARRATIVE = (
    "幼儿A拿起材料放在面前，用右手将材料推到左侧，又拉回原位，重复了三次。"
    "随后他把两件材料叠放在一起，抬头看向旁边的幼儿B，没有说话。"
)


def generate_narrative(
    area_code: str,
    media_type: str,
    duration_sec: Optional[int] = None,
) -> Dict:
    """
    根据素材生成客观白描。

    接口契约（换成真实 AI 时必须保持一致）：
      入参: area_code 区域代号 / media_type photo|video / duration_sec 视频秒数
      返回: {
        "narrative": str,      # 客观白描正文
        "is_mock": bool,       # 是否为 demo 模拟数据
        "engine": str,         # 生成引擎标识
        "notice": str,         # 给用户看的提示语
      }

    真实实现时替换这里：调 Dify 工作流 A，提示词要点见项目文档
      - 只描述看得见的动作、材料、语言、时长
      - 禁止评价性词汇（认真/专注/聪明/良好/较弱/有进步）
      - 禁止推测意图和情绪，除非有明确表情或语言证据
      - 用「幼儿A」「幼儿B」指代，不用真实姓名
    """
    text = _MOCK_NARRATIVES.get(area_code, _MOCK_DEFAULT_NARRATIVE)

    if media_type == "video" and duration_sec:
        minutes = duration_sec // 60
        text += f"（本段素材时长约 {minutes} 分 {duration_sec % 60} 秒。）"

    return {
        "narrative": text,
        "is_mock": True,
        "engine": "demo-mock-v1",
        "notice": "⚠️ 这是演示用的模拟白描，未调用真实 AI。接入大模型后此处会替换为真实生成结果。",
    }


# ============================================================
# 工作流 B：白描 + 区域 + 年龄段 → 候选指标
# ============================================================

def _hit_keywords(text: str, keywords: List[str]) -> int:
    """数一下白描里命中了几个关键词"""
    return sum(1 for k in keywords if k and k in text)


def _check_quant_rule(rule: Optional[Dict], duration_sec: Optional[int]) -> bool:
    """
    纯计算判定：不走模型，零幻觉。
    目前只支持 duration_sec 字段，用于指标 1.1 的层级分界（10分钟 / 30分钟）。
    """
    if not rule or duration_sec is None:
        return False
    if rule["field"] != "duration_sec":
        return False
    if rule["op"] == "<":
        return duration_sec < rule["value"]
    if rule["op"] == ">=":
        return duration_sec >= rule["value"]
    return False


def suggest_indicators(
    narrative: str,
    area_code: str,
    age_group: str,
    duration_sec: Optional[int] = None,
    top_n: int = 3,
) -> Dict:
    """
    根据白描推荐 2-3 个候选指标。

    接口契约（换成真实 AI 时必须保持一致）：
      返回: {
        "suggestions": [
            {"indicator_code", "indicator_name", "level", "level_desc",
             "confidence", "reason", "rank", "deterministic"}
        ],
        "quant_hits": [...],   # 纯计算命中的，前端应标为「系统判定」而非「AI 建议」
        "is_mock": bool, "engine": str, "notice": str,
      }

    当前 mock 的打分逻辑（一个可解释的规则基线）：
        得分 = 区域先验权重 × 0.5 + 关键词命中数 × 0.25 - 负例命中数 × 0.3
      置信度低于 0.40 的不返回 —— 宁可少给，也不硬猜。
      判不了就返回空数组，这是被允许的（弃权比乱猜好）。

    真实实现时替换这里：调 Dify 工作流 B（RAG 检索指标知识库），
    但保留区域先验收敛和 quant_rule 纯计算这两步 —— 它们不该交给模型。
    """
    prior = AREA_PRIOR.get(area_code, DEFAULT_PRIOR)

    # ---- 第一步：纯计算命中，扫全部指标，与区域无关 ----
    quant_hits = []
    for code, item in INDICATORS.items():
        for level, detail in item["levels"].items():
            if _check_quant_rule(detail["quant_rule"], duration_sec):
                quant_hits.append({
                    "indicator_code": code,
                    "indicator_name": item["name"],
                    "level": level,
                    "level_desc": detail["desc"],
                    "basis": f"duration_sec={duration_sec} 满足规则 {detail['quant_rule']['op']} {detail['quant_rule']['value']}",
                    "deterministic": True,
                })

    # ---- 第二步：区域先验收敛候选集，再逐个判层级 ----
    # 判层级的规则：从高阶往低阶找，第一个有正例命中且无负例的就选它。
    # 这样避免「初阶关键词太宽泛把高阶抢走」——初阶应该是没有高阶信号时的默认，
    # 而不是靠抢关键词得分。
    evidenced, prior_only = [], []

    for code, weight in prior.items():
        item = INDICATORS.get(code)
        if not item:
            continue

        chosen = None
        for level in (3, 2, 1):
            detail = item["levels"][level]
            pos = _hit_keywords(narrative, detail["keywords"])
            neg = _hit_keywords(narrative, detail["negative"])
            if pos > 0 and neg == 0:
                chosen = {
                    "level": level,
                    "desc": detail["desc"],
                    "pos": pos,
                    "confidence": round(min(0.95, weight * 0.5 + pos * 0.2), 3),
                }
                break

        if chosen:
            evidenced.append({
                "indicator_code": code,
                "indicator_name": item["name"],
                "level": chosen["level"],
                "level_desc": chosen["desc"],
                "confidence": chosen["confidence"],
                "reason": _build_reason(item["name"], chosen, area_code),
                "evidence_based": True,
            })
        else:
            # 白描里找不到任何层级信号 —— 只能靠区域先验猜，置信度压低并明说
            conf = round(min(0.42, weight * 0.45), 3)
            if conf >= 0.35:
                prior_only.append({
                    "indicator_code": code,
                    "indicator_name": item["name"],
                    "level": 1,
                    "level_desc": item["levels"][1]["desc"],
                    "confidence": conf,
                    "reason": (
                        f"白描中未出现「{item['name']}」的明确行为信号，"
                        f"仅依据「该区域高频触发此要点」推测，置信度低，请教师重点核对。"
                    ),
                    "evidence_based": False,
                })

    evidenced.sort(key=lambda x: x["confidence"], reverse=True)
    prior_only.sort(key=lambda x: x["confidence"], reverse=True)

    # 有证据的优先，不够 top_n 再用先验猜的补齐
    top = (evidenced + prior_only)[:top_n]
    for i, s_ in enumerate(top, start=1):
        s_["rank"] = i
        s_["deterministic"] = False

    return {
        "suggestions": top,
        "quant_hits": quant_hits,
        "is_mock": True,
        "engine": "demo-mock-rule-v1",
        "notice": "⚠️ 候选指标由演示用规则引擎生成（区域先验＋关键词命中），未调用真实 AI。",
        "evidence_based_count": len(evidenced),
    }


def _build_reason(name: str, best: Dict, area_code: str) -> str:
    """拼一句人能看懂的推荐理由 —— 让教师能快速判断要不要采纳"""
    lv = {1: "初阶", 2: "中阶", 3: "高阶"}[best["level"]]
    return f"白描中出现 {best['pos']} 处与「{name}·{lv}」相符的行为描述，且该区域高频触发此要点。"
