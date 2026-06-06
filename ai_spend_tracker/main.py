"""
AI Spend Tracker — CLI 入口
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import Optional

from ai_spend_tracker.collectors import get_all_collectors, get_collector
from ai_spend_tracker.config import init_user_dirs
from ai_spend_tracker.demo import generate_demo
from ai_spend_tracker.display import render_json, render_report

from rich.console import Console

console = Console()


def _parse_date(s: str) -> Optional[datetime]:
    """解析 YYYY-MM-DD 格式日期。"""
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        console.print(f"[red]Invalid date format: {s}. Use YYYY-MM-DD.[/red]")
        return None


def cmd_list_agents() -> None:
    collectors = get_all_collectors()

    if not collectors:
        console.print(
            "[yellow]No collectors found.[/yellow]\n"
            "Built-in collectors will appear once implemented.\n"
            "Place custom collectors in ~/.ai-spend/collectors/.\n"
            "Run [bold]ai-spend init[/bold] to create an example template."
        )
        return

    from rich.table import Table
    table = Table(title="Available Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Display Name", style="green")
    table.add_column("Description")
    table.add_column("Type", style="blue")

    for c in collectors:
        module_path = type(c).__module__
        ctype = "built-in" if module_path.startswith("ai_spend_tracker.") else "custom"
        table.add_row(c.name(), c.display_name(), c.description(), ctype)

    console.print(table)
    console.print(f"\nTotal: {len(collectors)} collector(s)")


def cmd_init(agent_name: str | None = None) -> None:
    init_user_dirs(agent_name)
    console.print("[green]~/.ai-spend/ initialized![/green]")
    console.print("Place custom collectors in: [bold]~/.ai-spend/collectors/[/bold]")
    console.print()
    console.print("Path overrides (if auto-detection fails):")
    console.print("  Create [bold]~/.ai-spend/config.json[/bold] with:")
    console.print(
        '  [dim]{"paths": {"hermes": "D:/custom/hermes/state.db",'
        ' "codex": "C:/Users/me/.codex/state_1.sqlite",'
        ' "copilot": "D:/copilot/session-store.db",'
        ' "opencode": "D:/opencode/opencode.db",'
        ' "claude-code": "D:/claude/projects",'
        ' "openclaw": "D:/.openclaw",'
        ' "kimi": "D:/.kimi"}}[/dim]'
    )


def cmd_report(
    agent_filter: Optional[str],
    days: int,
    since_str: Optional[str],
    until_str: Optional[str],
    output_format: str,
    demo: bool = False,
) -> None:
    # Demo 模式：生成示例数据
    if demo:
        console.print("[green]Demo mode — showing sample data[/green]")
        console.print()
        demo_records = generate_demo(days=days)

        # 按 agent 筛选（demo 也支持 --agent）
        if agent_filter:
            names = set(n.strip() for n in agent_filter.split(","))
            demo_records = [r for r in demo_records if r.source in names]

        if output_format == "json":
            print(render_json(demo_records))
        else:
            render_report(demo_records, since=None, until=None)
        return

    # 解析时间
    now = datetime.now(timezone.utc)
    until: Optional[datetime] = None
    since: Optional[datetime] = None

    if since_str:
        since = _parse_date(since_str)
        if since is None:
            return
    elif days > 0:
        since = now - timedelta(days=days)

    if until_str:
        until = _parse_date(until_str)
        if until is None:
            return
        # 把 until 设为该天的末尾
        until = until.replace(hour=23, minute=59, second=59)

    # 获取 collector
    if agent_filter:
        names = [n.strip() for n in agent_filter.split(",")]
        collectors = []
        for name in names:
            c = get_collector(name)
            if c:
                collectors.append(c)
            else:
                console.print(f"[yellow]Warning: collector '{name}' not found[/yellow]")
        if not collectors:
            console.print("[red]No valid collectors found.[/red]")
            return
    else:
        collectors = get_all_collectors()
        if not collectors:
            console.print(
                "[yellow]No collectors available.[/yellow]\n"
                "Run [bold]ai-spend init[/bold] to set up, or wait for built-in collectors."
            )
            return

    # 收集数据
    all_records = []
    collectors_with_warnings = []
    for c in collectors:
        try:
            records = c.collect(since=since, until=until)
            all_records.extend(records)
            if not records:
                warning = c.warning_hint() if hasattr(c, 'warning_hint') else None
                if warning:
                    collectors_with_warnings.append(warning)
        except Exception as e:
            console.print(f"[red]Error collecting from {c.name()}: {e}[/red]")

    if not all_records:
        console.print("[yellow]No session data found for the given period.[/yellow]")
        console.print("Try: [bold]ai-spend --days 30[/bold] or [bold]ai-spend --demo[/bold]")
        if collectors_with_warnings:
            console.print()
            for w in collectors_with_warnings:
                console.print(w)
        return

    # 显示 collectors 的提示（即使有数据）
    if collectors_with_warnings:
        console.print()
        for w in collectors_with_warnings:
            console.print(w)

    # 输出
    if output_format == "json":
        print(render_json(all_records))
    else:
        render_report(all_records, since=since, until=until)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-spend",
        description="Aggregate token usage & cost across all your AI coding agents.",
        epilog=(
            "Path override (if auto-detection fails):\n"
            "  Create ~/.ai-spend/config.json:\n"
            '    {"paths": {"hermes": "D:/custom/hermes/state.db",\n'
            '              "codex": "C:/Users/me/.codex/state_1.sqlite",\n'
            '              "copilot": "D:/copilot/session-store.db",\n'
            '              "opencode": "D:/opencode/opencode.db",\n'
            '              "claude-code": "D:/claude/projects",\n'
            '              "openclaw": "D:/.openclaw",\n'
            '              "kimi": "D:/.kimi"}}\n'
            "  Run 'ai-spend --init' for more details."
        ),
    )
    parser.add_argument(
        "--list-agents", action="store_true",
        help="List all available data collectors",
    )
    parser.add_argument(
        "--init", nargs="?", const=True, default=False,
        help="Initialize ~/.ai-spend/ directory (collectors template). Optionally specify a collector name: --init my-agent",
    )
    parser.add_argument(
        "--agent", type=str, default=None,
        help="Filter by agent name (comma-separated)",
    )
    parser.add_argument(
        "--days", type=int, default=7,
        help="Days to look back (default: 7). 0 = all time",
    )
    parser.add_argument(
        "--since", type=str, default=None,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--until", type=str, default=None,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--format", type=str, choices=["table", "json"], default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Show sample data (no real agents needed)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.init:
        agent_name = args.init if isinstance(args.init, str) else None
        cmd_init(agent_name)
        return

    if args.list_agents:
        cmd_list_agents()
        return

    cmd_report(
        agent_filter=args.agent,
        days=args.days,
        since_str=args.since,
        until_str=args.until,
        output_format=args.format,
        demo=args.demo,
    )


if __name__ == "__main__":
    main()
