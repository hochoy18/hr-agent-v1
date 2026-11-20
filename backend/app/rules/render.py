"""把规则文件渲染成提示词片段。

档位定义的唯一来源是 `interview_rules_v1.json`，提示词里的档位段落由本模块生成。
改判定口径只需改 JSON 并升 `rule_version`，不用再同步维护一份手写提示词。
"""

from typing import Any, Dict, List

from app.rules import load_rules

# 各档正例的标记，避免提示词里出现"positive/negative"这类与好坏混淆的措辞
_EXAMPLE_MARKS = (("hit", "✓ 算"), ("miss", "✗ 不算"), ("ambiguous", "? 拿不准"))


def _join(items: Any, sep: str = "；") -> str:
    """把规则里的列表项拼成一行，去掉句末句号避免拼接后出现"。。"。"""
    if not isinstance(items, list):
        return str(items or "")
    cleaned = [str(item).strip().rstrip("。") for item in items if str(item).strip()]
    return sep.join(cleaned)


def _render_examples(examples: Dict[str, List[str]]) -> str:
    parts = []
    for key, mark in _EXAMPLE_MARKS:
        values = [str(v).strip() for v in (examples.get(key) or []) if str(v).strip()]
        if values:
            parts.append(f"{mark}：{'／'.join(values[:2])}")
    return "｜".join(parts)


def render_field(field_name: str) -> str:
    """渲染一个判定字段（verdict / substance / followup）的全部档位定义。"""
    rules = load_rules()
    field = next(
        (item for item in rules.get("fields", []) if item.get("field") == field_name),
        None,
    )
    if field is None:
        raise KeyError(f"规则文件缺少字段：{field_name}")

    options = sorted(field.get("options") or [], key=lambda o: o.get("precedence", 99))
    if not options:
        raise ValueError(f"规则文件的字段 {field_name} 没有档位定义")

    lines = [
        f"**{field_name}**（{field.get('question') or field.get('label') or ''}）",
        "只能取：" + "、".join(str(option["value"]) for option in options),
    ]

    lookahead = field.get("lookahead")
    if lookahead:
        note = field.get("lookahead_note") or ""
        lines.append(f"判定视野：可看紧随其后的 {lookahead} 组。{note}".rstrip("；。"))

    lines.append("按下列顺序判断，靠前的先判，命中即停：")

    for option in options:
        tags = []
        if option.get("precedence") is not None:
            tags.append(f"判序 {option['precedence']}")
        if option.get("engine") == "rule":
            tags.append("由程序判定，模型结论会被覆盖")
        head = f"- **{option['value']}**"
        if tags:
            head += "（" + "，".join(tags) + "）"
        lines.append(head)

        if option.get("requires"):
            lines.append(f"  命中：{_join(option['requires'])}")
        if option.get("excludes"):
            lines.append(f"  不算：{_join(option['excludes'])}")
        examples = _render_examples(option.get("examples") or {})
        if examples:
            lines.append(f"  例：{examples}")

    return "\n".join(lines)


def render_qa_rubric() -> str:
    """问答判定的三个字段，拼成可直接嵌入提示词的一段。"""
    return "\n\n".join(render_field(name) for name in ("verdict", "substance", "followup"))


def _num(value: Any) -> str:
    """把权重/阈值写成最短形式：1.0 → 1、0.5 → 0.5。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number == int(number) else f"{number:g}"


def _positive_ratio_rule(spec: Dict[str, Any]) -> List[str]:
    """问答一致性：正面率的分子分母与档位阈值。"""
    weights = spec.get("weights") or {}
    zero_values = [name for name, weight in weights.items() if not float(weight or 0)]
    half_values = [name for name, weight in weights.items() if float(weight or 0) == 0.5]
    full_values = [name for name, weight in weights.items() if float(weight or 0) == 1]

    parts = []
    if full_values:
        parts.append(f"{'、'.join(full_values)}=1")
    if half_values:
        parts.append(f"{'、'.join(half_values)}=0.5")
    if zero_values:
        parts.append(f"{'、'.join(zero_values)}=0")
    lines = [f"- 正面率 ＝（{'，'.join(parts)}）之和 ÷ 有效判定的组数"]
    for band in sorted(spec.get("bands") or [], key=lambda b: -float(b["min"])):
        label = band.get("label") or ""
        lines.append(
            f"- 正面率 ≥{_num(band['min'])} → {_num(band['score'])} 档" + (f"：{label}" if label else "")
        )
    floor = spec.get("below_min_score")
    if floor is not None:
        floor_label = spec.get("below_min_label") or ""
        lowest = min(float(band["min"]) for band in spec.get("bands") or []) if spec.get("bands") else None
        condition = f"正面率 <{_num(lowest)}" if lowest is not None else "低于最低阈值"
        lines.append(
            f"- {condition} → {_num(floor)} 档" + (f"：{floor_label}" if floor_label else "")
        )
    return lines


def render_derivation_rubric() -> str:
    """把 derivation 与 dimension_weights 渲染成打分调用的"算分口径"段。

    问答一致性、事实信息量这两维的分数由程序按本段口径算出，模型输出会被覆盖；
    把同一段口径送进提示词，是为了让模型写的 reason 与最终分数对得上，而不是各按各的尺子。
    """
    rules = load_rules()
    derivation = rules.get("derivation") or {}
    lines = [
        f"判定统计口径（来自规则文件 {rules.get('rule_version') or '未标注'}，"
        "这两维的分数由程序按此算定，不要自行给分）",
        "",
    ]

    consistency = derivation.get("问答一致性") or {}
    if consistency:
        lines.append(f"**问答一致性**（数据源：{consistency.get('source', 'verdict')}）")
        lines.extend(_positive_ratio_rule(consistency))
        lines.append(f"- 有效判定不足 {_num(consistency.get('min_samples', 3))} 组时不推导")
        lines.append("")

    substance = derivation.get("事实信息量") or {}
    if substance:
        weights = substance.get("weights") or {}
        items = "、".join(f"{name} {_num(weight)}" for name, weight in weights.items())
        lines.append(f"**事实信息量**（数据源：{substance.get('source', 'substance')}）")
        lines.append(f"- 均值 ＝（{items}）之和 ÷ 参与计算的组数")
        if substance.get("band_note"):
            lines.append(f"- {substance['band_note'].rstrip('。')}")
        excluded = {
            group.get("group"): group.get("members") or []
            for group in rules.get("exclusive_groups") or []
        }
        exclude_group = substance.get("exclude_group")
        if exclude_group in excluded and excluded[exclude_group]:
            values = [str(item).split(":")[-1] for item in excluded[exclude_group]]
            lines.append(f"- 判定为「{'、'.join(values)}」的组不计入均值")
        lines.append(f"- 有效判定不足 {_num(substance.get('min_samples', 3))} 组时不推导")
        lines.append("")

    weights = (rules.get("dimension_weights") or {}).get("weights") or {}
    if weights:
        formula = " + ".join(f"{name} {round(float(weight) * 100)}%" for name, weight in weights.items())
        lines.append(f"**总分权重**：{formula}")

    return "\n".join(lines).strip()


def render_rule_header() -> str:
    """规则文件的版本与引擎约定，放在提示词开头便于回溯是哪一版口径。"""
    rules = load_rules()
    return (
        f"判定口径版本：{rules.get('rule_version') or '未标注'}"
        f"（标签版本 {rules.get('label_version') or '未标注'}）"
    )
