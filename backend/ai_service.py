"""AI 服务层：工作流 A 保持 mock，工作流 B 可切换 DeepSeek 或规则降级。"""

import json
import re
from time import perf_counter
from typing import List, Dict, Optional

import httpx

from config import AI_MODE, DEEPSEEK_API_KEY, DEEPSEEK_API_URL
from indicators import INDICATORS, AREA_PRIOR, DEFAULT_PRIOR
from prompts.workflow_b_v1 import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    render_full_prompt,
    render_user_prompt,
)
from time_utils import utc_now


DEEPSEEK_MODEL = "deepseek-chat"
# DeepSeek 官方对“数据抽取/数据分析”类任务的推荐值。
DEEPSEEK_TEMPERATURE = 1.0
DEEPSEEK_TIMEOUT_SECONDS = 30.0
DEEPSEEK_MAX_ATTEMPTS = 2  # 首次失败后重试 1 次
PRIOR_ONLY_PREFIX = "仅依据区域先验推测，请教师重点核对"


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


def _suggest_indicators_mock(
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

    该函数同时作为 DeepSeek 不可用时的稳定降级路径。
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


def _is_dimension_2(code: str, item: Dict) -> bool:
    """维度 2（社会情感）属于伦理硬排除项，不受配置影响。"""
    return code.split(".", 1)[0] == "2" or item.get("dimension") == "社会情感"


def _model_indicator_catalog() -> List[Dict]:
    """给模型全部可判定指标；区域先验绝不用于过滤候选集。"""
    catalog = []
    for code, item in INDICATORS.items():
        if _is_dimension_2(code, item):
            continue
        levels = []
        for level in (1, 2, 3):
            detail = item["levels"][level]
            levels.append({
                "level": level,
                "desc": detail["desc"],
                "keywords": detail["keywords"],
                "negative": detail["negative"],
            })
        catalog.append({
            "indicator_code": code,
            "indicator_name": item["name"],
            "dimension": item["dimension"],
            "levels": levels,
        })
    return catalog


def _extract_quoted_fragments(reason: str) -> List[str]:
    patterns = [
        r"“([^”]+)”",
        r'"([^"]+)"',
        r"‘([^’]+)’",
        r"'([^']+)'",
    ]
    fragments = []
    for pattern in patterns:
        fragments.extend(re.findall(pattern, reason))
    return [fragment.strip() for fragment in fragments if fragment.strip()]


def _loosely_contains(narrative: str, fragment: str) -> bool:
    """只忽略空白差异，不允许模型改写或拼接原文。"""
    normalize = lambda value: re.sub(r"\s+", "", value)  # noqa: E731
    return bool(fragment) and normalize(fragment) in normalize(narrative)


def _validate_model_suggestions(
    payload: Dict,
    *,
    narrative: str,
    top_n: int,
) -> tuple:
    """不信任模型输出：校验白名单、层级、置信度与原文引用。"""
    raw_suggestions = payload.get("suggestions")
    if not isinstance(raw_suggestions, list):
        raise ValueError("模型 JSON 缺少 suggestions 数组")

    allowed = {
        code: item
        for code, item in INDICATORS.items()
        if not _is_dimension_2(code, item)
    }
    valid = []
    warnings = []

    for index, raw in enumerate(raw_suggestions, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"第 {index} 条不是 JSON object，已丢弃")
            continue

        code = raw.get("indicator_code")
        if code not in allowed:
            warnings.append(f"第 {index} 条指标 {code!r} 不在允许清单中，已丢弃")
            continue

        level = raw.get("level")
        if isinstance(level, bool) or level not in {1, 2, 3}:
            warnings.append(f"第 {index} 条指标 {code} 的 level 非法，已丢弃")
            continue

        confidence = raw.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            warnings.append(f"第 {index} 条指标 {code} 的 confidence 非数字，已丢弃")
            continue
        confidence = float(confidence)
        if not 0 <= confidence <= 1:
            warnings.append(f"第 {index} 条指标 {code} 的 confidence 超出 0–1，已丢弃")
            continue

        reason = raw.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            warnings.append(f"第 {index} 条指标 {code} 缺少 reason，已丢弃")
            continue
        reason = reason.strip()

        fragments = _extract_quoted_fragments(reason)
        matching_fragments = [
            fragment
            for fragment in fragments
            if _loosely_contains(narrative, fragment)
        ]
        evidence_based = bool(matching_fragments)
        if evidence_based:
            # 模型可能先给出真实引用，再在引号外夹带无依据推断。
            # 只保留已通过原文检查的引用，避免“真引用掩护假解释”。
            reason = "白描原文：" + "；".join(
                f"“{fragment}”" for fragment in matching_fragments
            )
        else:
            if raw.get("evidence_based") is True:
                warnings.append(
                    f"第 {index} 条指标 {code} 的原文引用无法在白描中找到，"
                    "已降为区域先验"
                )
            confidence = min(confidence, 0.42)
            if not reason.startswith(PRIOR_ONLY_PREFIX):
                reason = f"{PRIOR_ONLY_PREFIX}：{reason}"

        item = allowed[code]
        valid.append({
            "indicator_code": code,
            "indicator_name": item["name"],
            "level": level,
            "level_desc": item["levels"][level]["desc"],
            "confidence": round(confidence, 3),
            "reason": reason,
            "evidence_based": evidence_based,
            "deterministic": False,
        })

    valid.sort(key=lambda item: item["confidence"], reverse=True)
    valid = valid[:top_n]
    for rank, item in enumerate(valid, start=1):
        item["rank"] = rank
    return valid, warnings


def _safe_response_json(response: httpx.Response) -> Dict:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}
    except (ValueError, json.JSONDecodeError):
        return {
            "http_status": response.status_code,
            "body": response.text[:2000],
        }


def _mock_run_metadata(result: Dict, started_at, elapsed_ms: int) -> Dict:
    return {
        "workflow": "indicator_suggestion",
        "provider": "mock",
        "model": "demo-mock-rule-v1",
        "prompt_version": PROMPT_VERSION,
        "status": "completed",
        "started_at": started_at,
        "completed_at": utc_now(),
        "latency_ms": elapsed_ms,
        "response_raw": {
            "suggestions": result["suggestions"],
            "quant_hits": result["quant_hits"],
        },
        "error_reason": None,
        "is_mock": True,
        "prompt_rendered": "mock 模式未向外部模型发送 prompt",
        "token_usage": None,
        "temperature": None,
    }


def _deepseek_or_fallback(
    *,
    narrative: str,
    area_code: str,
    area_name: str,
    age_group: str,
    duration_sec: Optional[int],
    top_n: int,
) -> Dict:
    started_at = utc_now()
    started_clock = perf_counter()
    catalog = _model_indicator_catalog()
    allowed_codes = {item["indicator_code"] for item in catalog}
    prior = AREA_PRIOR.get(area_code, DEFAULT_PRIOR)
    prior = {code: weight for code, weight in prior.items() if code in allowed_codes}
    user_prompt = render_user_prompt(
        narrative=narrative,
        area_name=area_name,
        age_group=age_group,
        indicators=catalog,
        area_prior=prior,
        top_n=top_n,
    )
    prompt_rendered = render_full_prompt(SYSTEM_PROMPT, user_prompt)
    request_body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": DEEPSEEK_TEMPERATURE,
        "response_format": {"type": "json_object"},
        "max_tokens": 1600,
        "stream": False,
    }

    errors = []
    last_raw_response = None
    if not DEEPSEEK_API_KEY:
        errors.append("DEEPSEEK_API_KEY 未配置")
    else:
        for attempt in range(1, DEEPSEEK_MAX_ATTEMPTS + 1):
            try:
                response = httpx.post(
                    DEEPSEEK_API_URL,
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                    timeout=DEEPSEEK_TIMEOUT_SECONDS,
                )
                last_raw_response = _safe_response_json(response)
                response.raise_for_status()
                choices = last_raw_response.get("choices") or []
                content = choices[0]["message"]["content"] if choices else ""
                if not content:
                    raise ValueError("模型返回了空 content")
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise ValueError("模型返回的 JSON 顶层不是 object")
                suggestions, warnings = _validate_model_suggestions(
                    parsed,
                    narrative=narrative,
                    top_n=top_n,
                )
                if not suggestions:
                    raise ValueError("模型结果校验后一条候选都不剩")

                baseline = _suggest_indicators_mock(
                    narrative=narrative,
                    area_code=area_code,
                    age_group=age_group,
                    duration_sec=duration_sec,
                    top_n=top_n,
                )
                baseline.update({
                    "suggestions": suggestions,
                    "is_mock": False,
                    "engine": DEEPSEEK_MODEL,
                    "notice": "候选指标由 DeepSeek 生成，请教师逐条核对。",
                    "evidence_based_count": sum(
                        1 for item in suggestions if item["evidence_based"]
                    ),
                    "ai_run": {
                        "workflow": "indicator_suggestion",
                        "provider": "deepseek",
                        "model": DEEPSEEK_MODEL,
                        "prompt_version": PROMPT_VERSION,
                        "status": "completed",
                        "started_at": started_at,
                        "completed_at": utc_now(),
                        "latency_ms": round((perf_counter() - started_clock) * 1000),
                        "response_raw": last_raw_response,
                        "error_reason": "; ".join(warnings) or None,
                        "is_mock": False,
                        "prompt_rendered": prompt_rendered,
                        "token_usage": last_raw_response.get("usage"),
                        "temperature": DEEPSEEK_TEMPERATURE,
                    },
                })
                return baseline
            except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                errors.append(f"第 {attempt} 次调用失败：{exc}")

    fallback = _suggest_indicators_mock(
        narrative=narrative,
        area_code=area_code,
        age_group=age_group,
        duration_sec=duration_sec,
        top_n=top_n,
    )
    fallback.update({
        "notice": "⚠️ DeepSeek 暂时不可用，已自动使用演示规则生成候选指标。",
        "ai_run": {
            "workflow": "indicator_suggestion",
            "provider": "deepseek",
            "model": DEEPSEEK_MODEL,
            "prompt_version": PROMPT_VERSION,
            "status": "failed",
            "started_at": started_at,
            "completed_at": utc_now(),
            "latency_ms": round((perf_counter() - started_clock) * 1000),
            "response_raw": last_raw_response,
            "error_reason": "; ".join(errors),
            "is_mock": True,
            "prompt_rendered": prompt_rendered,
            "token_usage": (
                last_raw_response.get("usage") if last_raw_response else None
            ),
            "temperature": DEEPSEEK_TEMPERATURE,
        },
    })
    return fallback


def suggest_indicators(
    narrative: str,
    area_code: str,
    age_group: str,
    duration_sec: Optional[int] = None,
    top_n: int = 3,
    area_name: Optional[str] = None,
) -> Dict:
    """按配置执行工作流 B；DeepSeek 失败时永远降级而不向上抛错。"""
    if AI_MODE == "deepseek":
        return _deepseek_or_fallback(
            narrative=narrative,
            area_code=area_code,
            area_name=area_name or area_code,
            age_group=age_group,
            duration_sec=duration_sec,
            top_n=top_n,
        )

    started_at = utc_now()
    started_clock = perf_counter()
    result = _suggest_indicators_mock(
        narrative=narrative,
        area_code=area_code,
        age_group=age_group,
        duration_sec=duration_sec,
        top_n=top_n,
    )
    result["ai_run"] = _mock_run_metadata(
        result,
        started_at,
        round((perf_counter() - started_clock) * 1000),
    )
    return result
