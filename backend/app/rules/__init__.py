"""规则文件的加载入口。

规则档位定义放在同目录的 JSON 里，代码与提示词都以它为准：
加载后返回原始 dict，调用方按 rule_version 记录本次评价用的是哪一版。
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

RULE_FILE = Path(__file__).with_name("interview_rules_v1.json")


@lru_cache(maxsize=1)
def load_rules(path: Path = RULE_FILE) -> Dict[str, Any]:
    """读取并缓存规则文件。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rule_version() -> str:
    """当前规则版本号，用于写入评价结果。"""
    return str(load_rules().get("rule_version") or "")
