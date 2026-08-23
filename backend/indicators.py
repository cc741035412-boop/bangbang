"""
观察指标字典
来源：《具身认知理论下的深度学习行为观察指引 3.0》（本人参与的市级课题成果，已重构为 AI 可判定形态）

原版是给老师读的长句描述，这里改造成机器能用的结构：
  - 每条带 keywords（正例信号）和 negative（负例，什么情况不算）
  - 部分带 quant_rule（纯计算规则，不走模型，零幻觉）
  - 另有 AREA_PRIOR：区域先验，把候选从全部要点收敛到 5-8 个

MVP 只收录 AI 判定难度为「易 / 中」的三个维度：
  维度1 身体参与、维度3 社会互动、维度4 认知建构
维度2 社会情感（情绪识别、自我管理）不做自动判定 —— 单段素材判不准，且有伦理风险。
"""

# ============================================================
# 指标字典
# code: 要点编号 / name: 要点名 / dimension: 所属维度
# levels: 1=初阶 2=中阶 3=高阶
# ============================================================

INDICATORS = {
    # ---------- 维度 1：身体参与 ----------
    "1.1": {
        "name": "身体行为参与度",
        "dimension": "身体参与",
        "levels": {
            1: {
                "desc": "无明确目的，短暂或偶尔参与游戏，持续时间短（每次 10 分钟以内）",
                "keywords": ["短暂", "看了看", "走开", "换了个", "很快就"],
                "negative": ["持续", "一直", "反复"],
                "quant_rule": {"field": "duration_sec", "op": "<", "value": 600},
            },
            2: {
                "desc": "能持续进行身体操作（每次 30 分钟以上），如持续搭高、反复挖沙",
                "keywords": ["持续", "一直", "反复", "不停"],
                "negative": [],
                "quant_rule": {"field": "duration_sec", "op": ">=", "value": 1800},
            },
            3: {
                "desc": "面对挑战或干扰时能坚持（跨天或同一天跨时段）游戏",
                "keywords": ["第二天", "隔天", "下午又", "继续昨天", "还想玩"],
                "negative": [],
                "quant_rule": None,
            },
        },
    },
    "1.2": {
        "name": "身体探索方式",
        "dimension": "身体参与",
        "levels": {
            1: {
                "desc": "单一感官探索：主要用一种感官（如看、摸）了解材料",
                "keywords": ["只是看", "看了看", "盯着"],
                "negative": ["又", "边…边", "同时"],
                "quant_rule": None,
            },
            2: {
                "desc": "多感官协同：同时使用两种或以上感官进行探索（边看边摸、闻一闻再敲一敲）",
                "keywords": ["边看边", "闻", "敲", "听", "又摸又"],
                "negative": [],
                "quant_rule": None,
            },
            3: {
                "desc": "将感官信息与身体动作紧密结合，深入探索（如听着声音变化调整敲击力度）",
                "keywords": ["调整力度", "根据声音", "轻一点", "重一点", "试了试再"],
                "negative": [],
                "quant_rule": None,
            },
        },
    },
    "1.3": {
        "name": "身体行为复杂性",
        "dimension": "身体参与",
        "levels": {
            1: {
                "desc": "重复性、练习性单一动作（搬运、堆放、填充、倾倒等）",
                "keywords": ["反复搬", "来回搬", "重复", "一次又一次", "又搬了"],
                "negative": ["连贯", "整合", "组合"],
                "quant_rule": None,
            },
            2: {
                "desc": "能熟练、连贯地操作材料（如装填—运输—倾倒）",
                "keywords": ["装满", "运到", "然后", "接着", "一连串"],
                "negative": [],
                "quant_rule": None,
            },
            3: {
                "desc": "整合多种复杂动作和材料，熟练完成综合操作",
                "keywords": ["组合", "拼接", "固定", "又…又…还", "多种材料"],
                "negative": [],
                "quant_rule": None,
            },
        },
    },
    "1.4": {
        "name": "身体行为目的性",
        "dimension": "身体参与",
        "levels": {
            1: {
                "desc": "无目的随意操作材料",
                "keywords": ["随意", "拿起又放下", "摆弄了一下"],
                "negative": ["为了", "想要", "打算"],
                "quant_rule": None,
            },
            2: {
                "desc": "能够有目的地根据常规用途和功能使用材料",
                "keywords": ["用来", "为了", "想搭", "打算"],
                "negative": [],
                "quant_rule": None,
            },
            3: {
                "desc": "突破材料常规用途，创造性使用或组合使用材料",
                "keywords": ["当作", "假装是", "变成", "他说这是", "不是…而是"],
                "negative": [],
                "quant_rule": None,
            },
        },
    },

    # ---------- 维度 3：社会互动 ----------
    "3.1": {
        "name": "互动形式",
        "dimension": "社会互动",
        "levels": {
            1: {
                "desc": "独自玩耍，或注视他人游戏但不参与",
                "keywords": ["独自", "一个人", "看着别人"],
                "negative": ["一起", "和同伴", "商量"],
                "quant_rule": None,
            },
            2: {
                "desc": "与同伴使用相似材料，在附近游戏但无直接互动",
                "keywords": ["各自", "在旁边玩", "互不"],
                "negative": [],
                "quant_rule": None,
            },
            3: {
                "desc": "与同伴交谈、分享材料、围绕共同目标游戏",
                "keywords": ["一起", "我们", "共同", "分工", "说"],
                "negative": [],
                "quant_rule": None,
            },
        },
    },
    "3.2": {
        "name": "互动策略与质量",
        "dimension": "社会互动",
        "levels": {
            1: {
                "desc": "在教师帮助下主动邀请同伴或提出玩法，能清晰回应他人邀请",
                "keywords": ["老师说", "在老师提醒下", "可以和你一起吗"],
                "negative": [],
                "quant_rule": None,
            },
            2: {
                "desc": "与同伴沟通，确定合作中的角色、活动、材料玩法，或接受分配的任务",
                "keywords": ["商量", "你来我来", "我搭这边", "谁当"],
                "negative": [],
                "quant_rule": None,
            },
            3: {
                "desc": "确定角色后坚持完成合作；遇困难时能与同伴分析原因并共同解决",
                "keywords": ["一起想办法", "共同解决", "坚持", "重新试"],
                "negative": [],
                "quant_rule": None,
            },
        },
    },
    "3.3": {
        "name": "规则意识",
        "dimension": "社会互动",
        "levels": {
            1: {
                "desc": "规则意识和安全意识较弱，经常需要教师提醒",
                "keywords": ["老师提醒", "又忘了", "跑到中间"],
                "negative": [],
                "quant_rule": None,
            },
            2: {
                "desc": "理解并主动遵守轮流、分享等基本规则，但有时需教师提醒",
                "keywords": ["排队", "轮流", "遵守", "记得"],
                "negative": [],
                "quant_rule": None,
            },
            3: {
                "desc": "独立遵守并维护约定的规则；主动提醒同伴或参与讨论制定规则",
                "keywords": ["提醒同伴", "不能超线", "轻一点", "一起定规则", "商量规则"],
                "negative": [],
                "quant_rule": None,
            },
        },
    },
    "3.7": {
        "name": "材料分享行为",
        "dimension": "社会互动",
        "levels": {
            1: {
                "desc": "多数时候能积极回应教师关于分享材料和轮流的提醒",
                "keywords": ["在老师提醒下分享"],
                "negative": [],
                "quant_rule": None,
            },
            2: {
                "desc": "主动分享材料维持游戏，愿意就玩什么、谁先玩进行简单商量",
                "keywords": ["给你", "一起用", "先给他"],
                "negative": [],
                "quant_rule": None,
            },
            3: {
                "desc": "材料有限时与同伴轮流使用",
                "keywords": ["轮流", "换我了", "你玩完给我"],
                "negative": [],
                "quant_rule": None,
            },
        },
    },

    # ---------- 维度 4：认知建构与发展 ----------
    "4.3": {
        "name": "分析与规划",
        "dimension": "认知建构",
        "levels": {
            1: {
                "desc": "游戏前没有明确计划，在游戏中边想边玩",
                "keywords": ["边玩边", "随手", "先拿了再说"],
                "negative": ["计划", "先画", "打算搭"],
                "quant_rule": None,
            },
            2: {
                "desc": "游戏前有简单构思或计划；游戏中能按功能或属性将材料分类摆放",
                "keywords": ["打算搭", "想搭一个", "分类", "先把…放一起"],
                "negative": [],
                "quant_rule": None,
            },
            3: {
                "desc": "游戏计划明确具体，游戏中会根据情况调整计划",
                "keywords": ["画了出来", "先画", "不是这样的", "要往这边", "调整"],
                "negative": [],
                "quant_rule": None,
            },
        },
    },
    "4.4": {
        "name": "试误与问题解决",
        "dimension": "认知建构",
        "levels": {
            1: {
                "desc": "遇到困难时，能主动用语言或动作寻求帮助",
                "keywords": ["老师帮", "求助", "怎么办"],
                "negative": [],
                "quant_rule": None,
            },
            2: {
                "desc": "通过反复尝试不同方法，坚持完成挑战性活动",
                "keywords": ["又试", "换了个", "再来一次", "反复尝试"],
                "negative": [],
                "quant_rule": None,
            },
            3: {
                "desc": "能以新颖方式使用材料，灵活解决新问题",
                "keywords": ["想到用", "换成", "发现可以", "把…当"],
                "negative": [],
                "quant_rule": None,
            },
        },
    },
    "4.6": {
        "name": "综合与创造",
        "dimension": "认知建构",
        "levels": {
            1: {
                "desc": "仿照示例进行操作，或对他人行为进行模仿性操作",
                "keywords": ["跟着", "照着", "学他"],
                "negative": [],
                "quant_rule": None,
            },
            2: {
                "desc": "在原有基础上进行个性化的修改和功能增加",
                "keywords": ["加了", "又装了", "改成", "多做了个"],
                "negative": [],
                "quant_rule": None,
            },
            3: {
                "desc": "围绕核心主题有规划地使用多种材料，创造结构复杂、细节丰富的综合作品",
                "keywords": ["主题", "装饰", "还有…还有", "整个", "做成了一个"],
                "negative": [],
                "quant_rule": None,
            },
        },
    },
}


# ============================================================
# 区域先验：这个区域高频触发哪些指标
# 作用是把 11 个候选要点收敛到 4-6 个，大幅提升判定精度
# 数字是权重 0~1，越大表示这个区域越容易出现该指标
# ============================================================

AREA_PRIOR = {
    "construction": {"1.3": 0.9, "1.4": 0.8, "4.3": 0.9, "4.6": 0.9, "3.2": 0.6},
    "sand_water":   {"1.2": 0.9, "1.3": 0.8, "4.4": 0.8, "3.7": 0.6, "1.1": 0.6},
    "climbing":     {"1.1": 0.9, "1.3": 0.7, "3.3": 0.8, "4.4": 0.5},
    "roleplay":     {"3.1": 0.9, "3.2": 0.9, "1.4": 0.8, "4.6": 0.7},
    "art":          {"1.2": 0.8, "4.6": 0.9, "1.3": 0.6, "4.3": 0.5},
    "reading":      {"3.1": 0.7, "4.3": 0.6, "1.2": 0.4},
    "science":      {"1.2": 0.9, "4.4": 0.9, "4.3": 0.7},
    "outdoor":      {"1.1": 0.9, "3.1": 0.7, "3.3": 0.9, "3.7": 0.7},
}

# 兜底：区域不在上表里时，用这一组通用指标
DEFAULT_PRIOR = {"1.3": 0.5, "1.4": 0.5, "3.1": 0.5, "4.4": 0.5}


def indicator_name(code: str) -> str:
    """按编号查要点名称"""
    return INDICATORS.get(code, {}).get("name", "未知指标")


def level_desc(code: str, level: int) -> str:
    """按编号 + 层级查行为描述"""
    return INDICATORS.get(code, {}).get("levels", {}).get(level, {}).get("desc", "")


def all_indicators_flat():
    """把字典摊平成列表，给 GET /indicators 接口用"""
    out = []
    for code, item in INDICATORS.items():
        for lv, detail in item["levels"].items():
            out.append({
                "indicator_code": code,
                "indicator_name": item["name"],
                "dimension": item["dimension"],
                "level": lv,
                "level_label": {1: "初阶", 2: "中阶", 3: "高阶"}[lv],
                "description": detail["desc"],
                "has_quant_rule": detail["quant_rule"] is not None,
            })
    return out
