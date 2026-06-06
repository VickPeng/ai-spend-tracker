"""
BaseCollector — 所有数据采集器的抽象基类。

内置 collector 放在 ai_spend_tracker/collectors/ 下，
用户自定义 collector 放在 ~/.ai-spend/collectors/ 下，
两者都继承此类即可自动被 CollectorRegistry 发现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from ai_spend_tracker.models import SessionRecord


# 常用模型定价表（USD per 1M input tokens）
# 用户自定义 collector 可以复用，也可以覆盖
DEFAULT_PRICING: dict[str, float] = {
    # DeepSeek
    "deepseek-v4-pro": 3.0,
    "deepseek-v4-flash": 0.5,
    "deepseek-v3.2": 2.0,
    "deepseek-v3.1": 2.0,
    "deepseek-v3": 2.0,
    "deepseek-r1": 4.0,
    # Qwen
    "qwen3.7-max": 4.0,
    "qwen3.6-max": 3.5,
    "qwen3.5-plus": 2.0,
    "qwen3.5-flash": 0.5,
    "qwen-max": 4.0,
    "qwen-plus": 2.0,
    "qwen-turbo": 0.5,
    "qwen3.5-omni-plus": 3.0,
    # MiniMax
    "MiniMax-M2.7": 3.0,
    "MiniMax-M2.5": 2.0,
    "MiniMax-M2.1": 1.0,
    # Claude
    "claude-sonnet-4-6": 15.0,
    "claude-sonnet-4": 15.0,
    "claude-opus-4": 15.0,
    "claude-opus-4-8": 15.0,
    "claude-sonnet-4.5": 15.0,
    "claude-haiku-3.5": 1.0,
    # Claude Code 内部模型别名
    "claude-sonnet-4-8": 15.0,
    "claude-opus-4-5": 15.0,
    # GitHub Copilot（常见模型）
    "gpt-5.4": 10.0,
    "gpt-5.5": 15.0,
    "gpt-5.1": 5.0,
    "claude-sonnet-4.5": 15.0,
    # Kimi (Moonshot AI)
    "kimi-for-coding": 4.0,
    "moonshot-k2.5": 4.0,
    "moonshot-k2.6": 4.0,
}


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str,
    pricing: dict[str, float] | None = None,
    output_multiplier: float = 4.0,
) -> float:
    """根据 token 用量和模型估算费用。"""
    table = pricing if pricing is not None else DEFAULT_PRICING
    price_per_1m_input = table.get(model, 2.0)
    cost_input = input_tokens / 1_000_000 * price_per_1m_input
    cost_output = output_tokens / 1_000_000 * price_per_1m_input * output_multiplier
    return round(cost_input + cost_output, 6)


class BaseCollector(ABC):
    """所有数据采集器必须实现此接口。"""

    @abstractmethod
    def name(self) -> str:
        """采集器名称，如 'hermes'、'codex'、'my-agent'。"""
        ...

    @abstractmethod
    def display_name(self) -> str:
        """用户友好的显示名称，如 'Hermes Agent'、'Codex CLI'。"""
        ...

    @abstractmethod
    def collect(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[SessionRecord]:
        """从数据源读取会话记录。"""
        ...

    def description(self) -> str:
        return self.display_name()

    def pricing_table(self) -> dict[str, float]:
        return DEFAULT_PRICING
