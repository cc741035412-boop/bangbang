"""工作流 A 视觉版 v4：多模态白描提示词模板。

状态说明：
- v4：改为"按观察对象聚焦"——只描写老师选择的观察对象幼儿（最多 N 名，画面中
  出现频率最高、持续时间最长者优先），其它幼儿一律不写；输出字数收紧到不超过 350 字。
- v3：把"忽略字幕/水印"强化为"当作不存在——不复述、不引用、不据此推断场景"；
  并新增"无内容帧（纯黑/纯白/看不清）直接跳过不写"。
- v2：改为"抽多帧 + 多图理解"，引导模型按时间顺序描述；并新增"忽略画面字幕/水印/剪辑标记"。
- 约束与 `ai_service.generate_narrative` docstring 一致，一字不改地落到系统提示里：
    只描述看得见的动作、材料、语言、时长；
    禁止评价性词汇（认真/专注/聪明/良好/较弱/有进步）；
    禁止推测意图和情绪，除非有明确表情或语言证据；
    用「幼儿A」「幼儿B」指代，不用真实姓名。
"""

from typing import List, Optional

PROMPT_VERSION = "wf-a-vision-v4"

SYSTEM_PROMPT = """你是幼儿园教师观察记录写作助手，只负责把一段素材写成客观白描，不是评价幼儿。

必须遵守：
1. 只描述画面里看得见的动作、材料、语言和时长；听得到的教师或幼儿原话要原文放进引号。
2. 禁止评价性词汇：认真、专注、聪明、良好、较弱、有进步、棒、厉害等一律不出现。
3. 禁止推测幼儿的意图、能力或情绪，除非画面/声音里有明确证据（如幼儿自己说了"我不玩了"）。
4. 幼儿一律用「幼儿A」「幼儿B」指代，禁止出现任何姓名。
5. 按时间顺序写，动作要有来龙去脉：先做了什么、接着发生什么、结果如何。
6. 没有明确行为信号的部分允许不写，禁止脑补、禁止硬猜。
7. 画面里的字幕、水印、剪辑软件叠加的文字/图标/标记属于非真实内容，一律当作不存在：
   不要复述、不要引用、不要根据它们推断场景或行为，只依据画面里真实发生的内容描述。
8. 纯黑、纯白、或完全看不清内容的画面属于无内容帧：直接跳过、不要写进白描，
   也不要描述"画面变黑""画面空白"这类现象。
9. 只描写画面中的观察对象幼儿（数量见用户提示）：优先写出现频率最高、持续时间最长的那几名，
   其他幼儿一律不要描写；若画面中无法区分具体人数，就写最可能被观察的那一名。"""


def render_user_prompt(
    *,
    area_name: str,
    media_type: str,
    duration_sec: Optional[int],
    frames: List[dict],
    transcript: Optional[str],
    child_count_hint: Optional[int] = None,
) -> str:
    """渲染发送给视觉模型的用户 prompt。

    frames: 视觉模型直接看到的画面帧列表，按时间顺序排列，每项形如
      {"timestamp_sec": float|None, "description": "...", ...}
     图片时 timestamp_sec 为 None；视频抽帧时带时间点。
    transcript: 教师/幼儿原话转写；无音频时为 None。
    child_count_hint: 观察对象幼儿的数量（老师选择的观察对象数），决定白描描写哪几个幼儿。
    画面以图片内容直接交给模型；这里用文字引导模型按时间顺序描述发生的事。
    """
    parts: List[str] = []
    parts.append(f"场景：{area_name}")
    parts.append(
        f"素材类型：{'视频' if media_type == 'video' else '照片'}"
        + (f"，时长约 {duration_sec} 秒" if duration_sec else "")
    )

    if frames:
        parts.append("\n画面（按时间顺序排列，请结合上面的画面内容）：")
        for frame in frames:
            ts = frame.get("timestamp_sec")
            stamp = f"[约 {ts} 秒]" if ts is not None else "[单张画面]"
            parts.append(f"{stamp}（见对应画面）")
        if media_type == "video":
            parts.append(
                "\n请按发生的时间顺序，把『从开始到结束』整个过程客观描述出来："
                "先发生了什么、接着发生了什么、结果如何。动作要有来龙去脉。"
            )
    else:
        parts.append("\n画面：无（请在对应接口注入图片内容）")

    if transcript:
        parts.append(f"\n声音原话（逐字转写，仅作上下文参考）：\n{transcript}")
    else:
        parts.append("\n声音：无音频或没有可听清的语言内容")

    if not child_count_hint:
        child_count_hint = 1
    parts.append(
        f"\n这是老师选择的观察对象，共 {child_count_hint} 名幼儿。"
        f"请只描写这 {child_count_hint} 名幼儿（画面中出现频率最高、持续时间最长的优先；"
        f"若可辨认的幼儿不足 {child_count_hint} 名，就把所有可辨认的都写出来），"
        "其他幼儿一律不要描写。按出现先后用幼儿A、幼儿B…指代，"
        "幼儿A 为最主要的观察对象。"
    )

    parts.append(
        "\n请输出一段客观白描，整段不超过 350 字。只输出白描正文本身，"
        "不要标题、不要「评价」结论、不要建议，不要出现真实姓名。"
    )
    return "\n".join(parts)


if __name__ == "__main__":
    # 自检示例：渲染一段带画面的 prompt，肉眼核对约束是否都在。
    print(render_user_prompt(
        area_name="建构区",
        media_type="video",
        duration_sec=2100,
        frames=[
            {"index": 1, "timestamp_sec": 0, "description": "一名幼儿从积木柜取来 4 块扇形积木"},
            {"index": 2, "timestamp_sec": 1050, "description": "幼儿将积木首尾相接拼成圆形"},
            {"index": 3, "timestamp_sec": 2100, "description": "另一名幼儿走近，两人分开两侧摆放长条积木"},
        ],
        transcript='幼儿A对走近的幼儿说"你搭那边"。',
        child_count_hint=2,
    ))
