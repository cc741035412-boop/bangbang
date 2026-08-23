"""工作流 B v2：确定性层级归系统，模型只判语义层级。"""

import json
from typing import Dict, List


PROMPT_VERSION = "wf-b-v2"

SYSTEM_PROMPT = """你是学前教育深度学习行为观察的标注助手。
你的职责是根据客观白描，从给定指标清单中找出有证据的候选指标，而不是评价幼儿。
你必须只输出一个合法 JSON object，不要输出 Markdown、代码围栏或 JSON 之外的说明。"""


def render_user_prompt(
    *,
    narrative: str,
    area_name: str,
    age_group: str,
    indicators: List[Dict],
    excluded_quant_levels: List[Dict],
    area_prior: Dict[str, float],
    top_n: int,
) -> str:
    """渲染实际发送给模型的用户 prompt。"""
    output_example = {
        "suggestions": [
            {
                "indicator_code": "4.4",
                "indicator_name": "试误与问题解决",
                "level": 2,
                "level_desc": "通过反复尝试不同方法，坚持完成挑战性活动",
                "confidence": 0.82,
                "reason": "白描原文写道：“他把沟挖深，水继续向前流”",
                "evidence_based": True,
                "rank": 1,
            }
        ]
    }

    return "\n".join([
        "请完成候选指标判定，并严格返回 JSON。",
        "",
        "【系统与模型的权责边界】",
        "凡配置 quant_rule 的“指标+层级”均由系统按客观数据计算，不在你的判定范围内。",
        "这些层级已从可判定清单删除。即使客观数据缺失，你也不得猜测或返回它们。",
        "同一指标中未配置 quant_rule 的其他层级，仍可依据白描进行语义判定。",
        "由系统管理、禁止模型返回的层级：",
        json.dumps(excluded_quant_levels, ensure_ascii=False, indent=2),
        "",
        "【输入】",
        f"客观白描：{narrative}",
        f"区域名称：{area_name}",
        f"年龄段：{age_group}",
        "可判定的指标清单：",
        json.dumps(indicators, ensure_ascii=False, indent=2),
        "该区域的先验权重表：",
        json.dumps(area_prior, ensure_ascii=False, indent=2),
        "区域先验只是提示信息，不是候选限制；不在先验表里的指标同样可以判定。",
        "",
        "【判定规则】",
        "1. 只能从给定的指标清单及其中实际列出的层级里选，禁止发明清单外的指标或层级。",
        "2. 对每个指标，只在清单列出的层级中按高阶(3) → 中阶(2) → 初阶(1)判定，取第一个能在白描中找到正例支撑的层级。",
        "3. 若某层级的 negative 负例在白描中命中，则该层级不成立，继续往下判。",
        "4. 所有可判定层级都没有支撑的指标，不要返回。",
        "5. 不得推断白描中没有描述的行为。白描没写的，就是没发生。",
        "",
        "【reason 字段硬要求】",
        "- 必须原样引用白描中的具体片段作为依据，用引号标出。",
        "- 不允许写“该行为体现了……”这类没有原文依据的空泛判断。",
        "- 引用片段必须真实存在于白描中，不得改写或拼接。",
        "",
        "【confidence 标准】",
        "- 0.70–0.90：白描中有明确、直接的行为描述支撑。",
        "- 0.43–0.69：白描中有间接线索，需要一定推断。",
        "- ≤0.42：白描中没有直接支撑，仅根据区域先验推测。此时 reason 必须以“仅依据区域先验推测，请教师重点核对”开头。",
        "",
        "【evidence_based 字段】",
        "- true：reason 中引用了白描原文。",
        "- false：仅依据区域先验。",
        "",
        f"最多返回 {top_n} 条，按 confidence 降序。宁可少给，也不要为了凑数硬猜——教师对“AI 乱猜”的容忍度极低。",
        "",
        "【JSON 输出结构示例】",
        json.dumps(output_example, ensure_ascii=False, indent=2),
    ])


def render_full_prompt(system_prompt: str, user_prompt: str) -> str:
    """保存完整 messages，确保日后能复盘实际请求内容。"""
    return json.dumps(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        ensure_ascii=False,
        indent=2,
    )
