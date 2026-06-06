"""
Demo — 生成示例数据，让新用户第一次看到工具效果。
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from ai_spend_tracker.models import SessionRecord

# 种子固定，每次生成的 demo 数据一致
random.seed(42)

AGENTS = ["hermes", "codex", "claude-code", "cursor"]

AGENT_DISPLAY = {
    "hermes": "Hermes Agent",
    "codex": "Codex CLI",
    "claude-code": "Claude Code",
    "cursor": "Cursor",
}

MODELS_BY_AGENT = {
    "hermes": [
        ("deepseek-v4-pro", 3.0),
        ("deepseek-v4-flash", 0.5),
        ("qwen3.7-max", 4.0),
    ],
    "codex": [
        ("gpt-5.5", 15.0),
        ("gpt-5.4", 10.0),
        ("qwen3.5-plus", 2.0),
    ],
    "claude-code": [
        ("claude-sonnet-4-6", 15.0),
        ("claude-haiku-3-5", 1.0),
    ],
    "cursor": [
        ("gpt-5.5", 15.0),
        ("claude-sonnet-4-6", 15.0),
    ],
}


def _random_session(
    agent: str,
    base_time: datetime,
    day_offset: int,
    session_idx: int,
) -> SessionRecord:
    """生成一条模拟会话记录。"""
    models = MODELS_BY_AGENT[agent]
    model_name, price = random.choice(models)

    # 随机 token 用量，不同模型分布不同
    if "flash" in model_name or "haiku" in model_name:
        base_input = random.randint(5_000, 50_000)
    elif "pro" in model_name or "sonnet" in model_name or "opus" in model_name:
        base_input = random.randint(50_000, 500_000)
    else:
        base_input = random.randint(10_000, 100_000)

    # 输出约为输入的 15-25%
    ratio = random.uniform(0.15, 0.25)
    output = int(base_input * ratio)

    # 费用
    cost_input = base_input / 1_000_000 * price
    cost_output = output / 1_000_000 * price * 4  # output 4x
    cost = round(cost_input + cost_output, 6)

    # 时间
    day_start = base_time - timedelta(days=day_offset)
    hour = random.randint(6, 23)
    minute = random.randint(0, 59)
    started = day_start.replace(hour=hour, minute=minute, second=0, microsecond=0)
    duration_minutes = random.randint(1, 30)
    ended = started + timedelta(minutes=duration_minutes)

    return SessionRecord(
        session_id=f"demo-{agent}-{day_offset}-{session_idx}",
        source=agent,
        model=model_name,
        started_at=started,
        ended_at=ended,
        input_tokens=base_input,
        output_tokens=output,
        cache_read_tokens=random.randint(0, base_input * 2),
        cache_write_tokens=random.randint(0, 50000),
        reasoning_tokens=random.randint(0, output * 2) if "deepseek" in model_name else 0,
        cost_usd=cost,
        api_calls=random.randint(1, 5),
    )


def generate_demo(days: int = 14) -> list[SessionRecord]:
    """生成演示用的示例数据。

    Args:
        days: 模拟的天数

    Returns:
        示例 SessionRecord 列表
    """
    now = datetime.now(timezone.utc)
    records: list[SessionRecord] = []

    for agent in AGENTS:
        # 每天随机 1-8 条会话
        for d in range(days):
            num_sessions = random.choices(
                [0, 1, 2, 3, 4, 5, 6],
                weights=[5, 15, 25, 25, 15, 10, 5],
            )[0]
            for i in range(num_sessions):
                records.append(_random_session(agent, now, d, i))

    return records
