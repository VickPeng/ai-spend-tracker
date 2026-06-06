"""
Display — 终端输出格式化（rich 表格）。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console
from rich.table import Table

from ai_spend_tracker.models import AggregatedStats, SessionRecord

console = Console()


def _aggregate(
    records: list[SessionRecord],
    period: str = "total",
) -> AggregatedStats:
    """将 SessionRecord 列表聚合成 AggregatedStats。"""
    stats = AggregatedStats()
    for r in records:
        stats.add_session(r)
    return stats


def _human_number(n: int) -> str:
    """格式化大数字：1234567 → 1,234,567"""
    return f"{n:,}"


def _compact_number(n: int) -> str:
    """紧凑格式化：1234 → 1.2K, 1234567 → 1.2M"""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def render_report(
    records: list[SessionRecord],
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> None:
    """输出完整报告。"""
    if not records:
        console.print("[yellow]No session data found for the given period.[/yellow]")
        return

    # ── 标题 ──
    period_str = ""
    if since and until:
        period_str = f"  {since.strftime('%Y-%m-%d')} ~ {until.strftime('%Y-%m-%d')}"
    elif since:
        period_str = f"  Since {since.strftime('%Y-%m-%d')}"

    console.print()
    console.print(
        f"[bold]AI Spend Tracker[/bold] — 用量汇总{period_str}"
    )
    console.print(f"[dim]Total: {len(records)} sessions from {len(set(r.source for r in records))} agent(s)[/dim]")
    console.print()

    # ── 按 Agent 汇总 ──
    by_agent: dict[str, list[SessionRecord]] = defaultdict(list)
    for r in records:
        by_agent[r.source].append(r)

    agent_table = Table(show_header=True, header_style="bold cyan")
    agent_table.add_column("Agent", style="green")
    agent_table.add_column("Sessions", justify="right")
    agent_table.add_column("Input Tokens", justify="right")
    agent_table.add_column("Output Tokens", justify="right")
    agent_table.add_column("Tokens Total", justify="right")
    agent_table.add_column("Cost (USD)", justify="right")

    grand_total = AggregatedStats()
    for agent_name in sorted(by_agent.keys()):
        agent_records = by_agent[agent_name]
        stats = _aggregate(agent_records)
        grand_total.merge(stats)
        agent_table.add_row(
            agent_name,
            str(stats.total_sessions),
            _compact_number(stats.total_input_tokens),
            _compact_number(stats.total_output_tokens),
            _compact_number(stats.total_tokens),
            f"${stats.total_cost_usd:.4f}",
        )

    agent_table.add_section()
    agent_table.add_row(
        "[bold]Total[/bold]",
        str(grand_total.total_sessions),
        _compact_number(grand_total.total_input_tokens),
        _compact_number(grand_total.total_output_tokens),
        _compact_number(grand_total.total_tokens),
        f"[bold]${grand_total.total_cost_usd:.4f}[/bold]",
    )
    console.print(agent_table)
    console.print()

    # ── 按模型汇总 ──
    by_model: dict[str, list[SessionRecord]] = defaultdict(list)
    for r in records:
        by_model[r.model].append(r)

    model_table = Table(show_header=True, header_style="bold cyan")
    model_table.add_column("Model", style="yellow")
    model_table.add_column("Sessions", justify="right")
    model_table.add_column("Input", justify="right")
    model_table.add_column("Output", justify="right")
    model_table.add_column("Cache R", justify="right")
    model_table.add_column("Cache W", justify="right")
    model_table.add_column("Reason", justify="right")
    model_table.add_column("Cost", justify="right")

    for model_name in sorted(by_model.keys()):
        m_records = by_model[model_name]
        stats = _aggregate(m_records)
        model_table.add_row(
            model_name[:30],
            str(stats.total_sessions),
            _compact_number(stats.total_input_tokens),
            _compact_number(stats.total_output_tokens),
            _compact_number(stats.total_cache_read),
            _compact_number(stats.total_cache_write),
            _compact_number(stats.total_reasoning_tokens),
            f"${stats.total_cost_usd:.4f}",
        )

    console.print(model_table)
    console.print()

    # ── 每日趋势 ──
    by_day: dict[str, list[SessionRecord]] = defaultdict(list)
    for r in records:
        if r.started_at:
            day_key = r.started_at.strftime("%m-%d")
            by_day[day_key].append(r)

    if by_day:
        day_table = Table(show_header=True, header_style="bold cyan")
        day_table.add_column("Date", style="white")
        day_table.add_column("Sessions", justify="right")
        day_table.add_column("Tokens", justify="right")
        day_table.add_column("Cost", justify="right")

        for day in sorted(by_day.keys()):
            d_records = by_day[day]
            stats = _aggregate(d_records)
            day_table.add_row(
                day,
                str(stats.total_sessions),
                _compact_number(stats.total_tokens),
                f"${stats.total_cost_usd:.4f}",
            )

        console.print(day_table)
        console.print()


def render_json(records: list[SessionRecord]) -> str:
    """输出 JSON 格式。"""
    import json
    data = []
    for r in records:
        data.append({
            "session_id": r.session_id,
            "source": r.source,
            "model": r.model,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cache_read_tokens": r.cache_read_tokens,
            "cache_write_tokens": r.cache_write_tokens,
            "reasoning_tokens": r.reasoning_tokens,
            "cost_usd": r.cost_usd,
            "api_calls": r.api_calls,
        })
    return json.dumps(data, indent=2, ensure_ascii=False)
