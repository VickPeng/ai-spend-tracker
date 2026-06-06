"""
ClaudeCodeCollector — 从 Claude Code 的 JSONL 会话日志读取用量数据。

数据位置：~/.claude/projects/<project>/<session-id>.jsonl

JSONL 记录类型：
  type=assistant → message.usage 包含 input_tokens, output_tokens, cache_* 等
  type=user      → 用户消息
  type=system    → 系统消息，含 durationMs

assistant 记录的 message.usage 格式：
  {
    "input_tokens": 28908,
    "output_tokens": 152,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    ...
  }
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai_spend_tracker.collectors.base import DEFAULT_PRICING, BaseCollector, estimate_cost
from ai_spend_tracker.config import get_path_override
from ai_spend_tracker.models import SessionRecord

# Cache read 按 input 价格的 10% 计费
CACHE_READ_DISCOUNT = 0.10

# Claude 缓存价格倍率


def _find_windows_claude_projects() -> Path | None:
    """从 WSL 内查找 Windows 侧的 ~/.claude/projects。"""
    mnt_users = Path("/mnt/c/Users")
    if not mnt_users.exists():
        return None
    wsl_user = os.environ.get("USER", "")
    if wsl_user:
        p = mnt_users / wsl_user / ".claude" / "projects"
        try:
            if p.is_dir():
                return p
        except PermissionError:
            pass
    try:
        candidates = sorted(
            [c for c in mnt_users.iterdir() if c.is_dir() and not c.name.startswith(".")],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
    except PermissionError:
        candidates = []
    for base in candidates:
        p = base / ".claude" / "projects"
        try:
            if p.is_dir():
                return p
        except PermissionError:
            continue
    return None


def claude_projects_dir() -> Path | None:
    """查找 Claude Code 的 projects 目录。"""
    override = get_path_override("claude-code")
    if override:
        if override.is_dir():
            return override
        return override.parent if override.suffix == ".jsonl" else None

    # 2. Linux / macOS
    default_path = Path.home() / ".claude" / "projects"
    if default_path.is_dir():
        return default_path

    # 3. macOS（~/Library/Application Support/ 备用）
    mac_path = Path.home() / "Library" / "Application Support" / "claude" / "projects"
    if mac_path.is_dir():
        return mac_path

    # 4. Windows（通过 /mnt/c/）
    win_path = _find_windows_claude_projects()
    if win_path:
        return win_path

    return None


def _parse_timestamp(ts_str: str | None) -> datetime | None:
    """解析 ISO 时间戳。"""
    if not ts_str:
        return None
    try:
        # "2026-05-13T13:33:30.419Z" or with timezone offset
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    try:
        # Try parsing with fractional seconds
        from datetime import timezone as tz
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(ts_str, fmt)
                if not dt.tzinfo:
                    dt = dt.replace(tzinfo=tz.utc)
                return dt
            except ValueError:
                continue
    except Exception:
        pass
    return None


class ClaudeCodeCollector(BaseCollector):
    """采集 Claude Code 的 token 用量数据。"""

    def name(self) -> str:
        return "claude-code"

    def display_name(self) -> str:
        return "Claude Code"

    def description(self) -> str:
        return "Claude Code — JSONL session logs in ~/.claude/projects/"

    def warning_hint(self) -> str | None:
        """检查 Claude Code 是否已安装但无数据，给出提示。"""
        # 检查 claude 命令是否存在
        claude_installed = False
        if os.name == "nt":
            claude_installed = (
                os.system("where claude >nul 2>nul") == 0
                or os.system("claude --version >nul 2>nul") == 0
            )
        else:
            claude_installed = (
                os.system("command -v claude >/dev/null 2>&1") == 0
            )

        if not claude_installed:
            return None

        # Claude Code 已安装但没有会话数据
        return (
            "[yellow]⚠ Claude Code is installed but no recent session data was found.[/yellow]\n"
            "  Claude Code v2.1.140+ may not persist session logs to disk.\n"
            "  Try [bold]--days 0[/bold] to see all historical data.\n"
            "  Sessions are only tracked if they exist in [dim]~/.claude/projects/[/dim]\n"
            "  See: [underline]https://github.com/anthropics/claude-code/issues/25941[/underline]"
        )

    def collect(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[SessionRecord]:
        projects_dir = claude_projects_dir()
        if projects_dir is None or not projects_dir.is_dir():
            return []

        records: list[SessionRecord] = []

        for project_dir in sorted(projects_dir.iterdir()):
            if not project_dir.is_dir() or project_dir.name.startswith("."):
                continue

            for jsonl_file in sorted(project_dir.glob("*.jsonl")):
                if not jsonl_file.is_file():
                    continue

                session_id = jsonl_file.stem
                session_start: Optional[datetime] = None
                session_end: Optional[datetime] = None
                models: set[str] = set()
                total_input = 0
                total_output = 0
                total_cache_read = 0
                total_cache_write = 0
                total_cost = 0.0
                assistant_msg_count = 0

                try:
                    with open(jsonl_file, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                entry = json.loads(line)
                            except json.JSONDecodeError:
                                continue

                            entry_type = entry.get("type", "")
                            ts = _parse_timestamp(entry.get("timestamp"))
                            if ts:
                                if session_start is None or ts < session_start:
                                    session_start = ts
                                if session_end is None or ts > session_end:
                                    session_end = ts

                            if entry_type == "assistant":
                                msg = entry.get("message") or {}
                                usage = msg.get("usage") or {}
                                model = (msg.get("model") or "").strip()
                                if model:
                                    models.add(model)

                                inp = usage.get("input_tokens", 0) or 0
                                out = usage.get("output_tokens", 0) or 0
                                cache_r = usage.get("cache_read_input_tokens", 0) or 0
                                cache_w = usage.get("cache_creation_input_tokens", 0) or 0

                                total_input += inp
                                total_output += out
                                total_cache_read += cache_r
                                total_cache_write += cache_w
                                assistant_msg_count += 1

                    if assistant_msg_count == 0:
                        continue

                    if since and session_start and session_start < since:
                        continue
                    if until and session_start and session_start > until:
                        continue

                    # 计算费用
                    model_str = ",".join(sorted(models)) if models else "unknown"
                    price_table = DEFAULT_PRICING
                    for model_name in models:
                        base_cost = estimate_cost(
                            input_tokens=total_input,
                            output_tokens=total_output,
                            model=model_name,
                        )
                        price = price_table.get(model_name, 2.0)
                        cache_read_cost = (
                            total_cache_read / 1_000_000 * price * CACHE_READ_DISCOUNT
                        )
                        total_cost += (base_cost + cache_read_cost) / len(models)

                    records.append(
                        SessionRecord(
                            session_id=session_id,
                            source=self.name(),
                            model=model_str,
                            started_at=session_start,
                            ended_at=session_end,
                            input_tokens=total_input,
                            output_tokens=total_output,
                            cache_read_tokens=total_cache_read,
                            cache_write_tokens=total_cache_write,
                            cost_usd=round(total_cost, 6),
                            api_calls=assistant_msg_count,
                        )
                    )

                except (OSError, PermissionError):
                    continue

        return records
