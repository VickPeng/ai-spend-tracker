"""
路径配置和目录初始化。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


# ---------------------------------------------------------------------------
# 用户配置覆盖（~/.ai-spend/config.json）
# 当自动探测找不到数据源时，用户可以手动指定路径
#
# 格式：
#   {"paths": {"hermes": "D:/custom/hermes/state.db",
#              "codex": "C:/Users/me/.codex/state_1.sqlite",
#              "claude-code": "/home/user/claude/usage.db"}}
# ---------------------------------------------------------------------------

def _load_user_config() -> dict:
    """加载 ~/.ai-spend/config.json（可选）。"""
    cfg_file = Path.home() / ".ai-spend" / "config.json"
    try:
        if cfg_file.exists():
            with open(cfg_file) as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def get_path_override(agent_name: str) -> Path | None:
    """检查用户是否在 config.json 中手动指定了 collector 的数据源路径。"""
    cfg = _load_user_config()
    raw = cfg.get("paths", {}).get(agent_name)
    if not raw:
        return None
    try:
        p = Path(raw).expanduser().resolve()
        if p.exists():
            return p
    except Exception:
        pass
    return None


def _find_wsl_state_db() -> Path | None:
    """When running on Windows, find Hermes state.db via WSL network path."""
    if sys.platform != "win32":
        return None
    try:
        # 获取默认 WSL 发行版名称
        result = subprocess.run(
            ["wsl.exe", "--list", "--quiet"],
            capture_output=True, timeout=15
        )
        raw = result.stdout
        # wsl.exe --list 输出可能是 UTF-16-LE 或 UTF-8
        if b"\x00" in raw:
            distro = raw.decode("utf-16-le", errors="replace").strip().split("\n")[0].strip()
        else:
            distro = raw.decode("utf-8", errors="replace").strip().split("\n")[0].strip()
        if not distro:
            return None

        # 在 WSL 内查询实际的 state.db 路径（尊重 $HERMES_HOME 和 $HOME）
        query_result = subprocess.run(
            ["wsl.exe", "-d", distro, "sh", "-c",
             'echo "${HERMES_HOME:-$HOME/.hermes}/state.db"'],
            capture_output=True, timeout=15
        )
        raw_path = query_result.stdout
        if b"\x00" in raw_path:
            wsl_path = raw_path.decode("utf-16-le", errors="replace").strip().split("\n")[0].strip()
        else:
            wsl_path = raw_path.decode("utf-8", errors="replace").strip().split("\n")[0].strip()
        if not wsl_path or not wsl_path.startswith("/"):
            return None

        # 去掉前导 /，构造 UNC 路径：\\wsl.localhost\<distro>\home\vick\.hermes\state.db
        unc_rel = wsl_path.lstrip("/")
        for base in [r"\\wsl.localhost", r"\\wsl$"]:
            p = Path(f"{base}\\{distro}\\{unc_rel}")
            if p.exists():
                return p
    except Exception:
        pass
    return None


def hermes_db_path() -> Path | None:
    # 1. 用户手动覆盖
    override = get_path_override("hermes")
    if override:
        return override

    # 2. Linux / macOS：~/.hermes/state.db
    default_path = Path.home() / ".hermes" / "state.db"
    if default_path.exists():
        return default_path

    # 3. macOS（~/Library/Application Support/ 备用）
    mac_path = Path.home() / "Library" / "Application Support" / "hermes" / "state.db"
    if mac_path.exists():
        return mac_path

    # 4. Windows 原生路径（C:\Users\<user>\.hermes\state.db）
    win_home = _wsl_windows_home()
    if win_home:
        win_path = win_home / ".hermes" / "state.db"
        if win_path.exists():
            return win_path

    # 5. Windows → WSL 网络路径（\\wsl.localhost\...）
    if sys.platform == "win32":
        wsl_net = _find_wsl_state_db()
        if wsl_net:
            return wsl_net

    return None


def codex_state_db_path() -> Path | None:
    # 1. 用户手动覆盖
    override = get_path_override("codex")
    if override:
        return override

    # 2. Linux / macOS
    for base in [Path.home(), Path.home() / "Library" / "Application Support"]:
        codex_dir = base / ".codex"
        if not codex_dir.exists():
            continue
        sqlites = sorted(codex_dir.glob("state_*.sqlite"))
        if sqlites:
            return sqlites[-1]

    # 3. Windows（通过 WSL /mnt/c/）
    win_home = _wsl_windows_home()
    for base in [win_home]:
        if not base:
            continue
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
