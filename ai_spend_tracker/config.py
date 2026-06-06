"""
路径配置和目录初始化。
"""

from __future__ import annotations

import os
from pathlib import Path


def user_data_dir() -> Path:
    path = Path.home() / ".ai-spend"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_collectors_dir() -> Path:
    path = user_data_dir() / "collectors"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _wsl_windows_home() -> Path:
    wsl_mnt = Path("/mnt/c/Users")
    if wsl_mnt.exists():
        wsl_user = os.environ.get("USER", "")
        if (wsl_mnt / wsl_user).exists():
            return wsl_mnt / wsl_user
        candidates = sorted(
            wsl_mnt.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
        )
        for c in candidates:
            if c.is_dir() and not c.name.startswith("."):
                return c
    return Path()


def hermes_db_path() -> Path | None:
    wsl_path = Path.home() / ".hermes" / "state.db"
    if wsl_path.exists():
        return wsl_path
    win_home = _wsl_windows_home()
    if win_home:
        win_path = win_home / ".hermes" / "state.db"
        if win_path.exists():
            return win_path
    return None


def codex_state_db_path() -> Path | None:
    win_home = _wsl_windows_home()
    for base in [Path.home(), win_home]:
        codex_dir = base / ".codex"
        if not codex_dir.exists():
            continue
        sqlites = sorted(codex_dir.glob("state_*.sqlite"))
        if sqlites:
            return sqlites[-1]
    return None


def _collector_template(name: str) -> str:
    safe_name = name.replace("-", "_")
    display = name.replace("_", " ").replace("-", " ").title()
    class_name = safe_name.title().replace("_", "")
    return f'''"""
Custom collector: {name}

Track token usage for your own AI agent.
Implement the BaseCollector interface below.
"""
from ai_spend_tracker.collectors.base import BaseCollector, estimate_cost
from ai_spend_tracker.models import SessionRecord
from datetime import datetime
from typing import Optional


class {class_name}Collector(BaseCollector):
    """Track token usage for {display}."""

    def name(self) -> str:
        return "{name}"

    def display_name(self) -> str:
        return "{display}"

    def description(self) -> str:
        return "Custom collector for {display}"

    def pricing_table(self) -> dict[str, float]:
        # Customize pricing for your models here
        return {{
            "my-model": 5.0,
        }}

    def collect(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[SessionRecord]:
        """
        TODO: Replace with your actual data source logic.

        Common patterns:
        1. SQLite: sqlite3.connect("path/to/logs.db")
        2. JSONL:  json.loads(line) for each line
        3. CSV:    csv.DictReader(open("path/to/file.csv"))
        4. API:    requests.get("https://your-api.com/usage")
        """
        return []
'''


def init_user_dirs(agent_name: str | None = None) -> None:
    """初始化用户目录结构。如果指定 agent_name，生成对应名称的模板文件。"""
    collectors = user_collectors_dir()

    # 确保 __init__.py 存在
    init_file = collectors / "__init__.py"
    if not init_file.exists():
        init_file.write_text("# ai-spend custom collectors\n")

    # 确定目标文件名
    if agent_name:
        target = collectors / f"{agent_name}.py"
        if target.exists():
            print(f"[yellow]Collector '{agent_name}' already exists: {target}[/yellow]")
            return
    else:
        target = collectors / "example.py"
        if target.exists():
            print("[yellow]~/.ai-spend/ already initialized. Use 'ai-spend init <name>' to create a new collector.[/yellow]")
            return

    target.write_text(_collector_template(agent_name or "my_agent"))
    print(f"[green]Created:[/green] {target}")
    print(f"Now implement the collect() method and run: [bold]ai-spend --list-agents[/bold]")
