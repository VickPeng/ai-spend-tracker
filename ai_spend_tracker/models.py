"""
AI Spend Tracker — 统一数据模型
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SessionRecord:
    """单个 AI agent 会话的 token 用量和费用记录。所有 collector 都输出此格式。"""

    session_id: str
    source: str  # collector name, e.g. "hermes", "codex"
    model: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    api_calls: int = 0


@dataclass
class AggregatedStats:
    """聚合统计，支持按 agent / 模型 / 日期分组嵌套。"""

    total_sessions: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read: int = 0
    total_cache_write: int = 0
    total_reasoning_tokens: int = 0
    total_cost_usd: float = 0.0
    total_api_calls: int = 0

    def add_session(self, session: SessionRecord) -> None:
        self.total_sessions += 1
        self.total_input_tokens += session.input_tokens
        self.total_output_tokens += session.output_tokens
        self.total_cache_read += session.cache_read_tokens
        self.total_cache_write += session.cache_write_tokens
        self.total_reasoning_tokens += session.reasoning_tokens
        self.total_cost_usd += session.cost_usd
        self.total_api_calls += session.api_calls

    def merge(self, other: "AggregatedStats") -> None:
        self.total_sessions += other.total_sessions
        self.total_input_tokens += other.total_input_tokens
        self.total_output_tokens += other.total_output_tokens
        self.total_cache_read += other.total_cache_read
        self.total_cache_write += other.total_cache_write
        self.total_reasoning_tokens += other.total_reasoning_tokens
        self.total_cost_usd += other.total_cost_usd
        self.total_api_calls += other.total_api_calls

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens
