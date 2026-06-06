"""
CopilotCollector — 从 GitHub Copilot CLI 的本地 session 数据读取用量。

数据来源：
  1. ~/.copilot/session-store.db（SQLite）— 会话元数据
  2. ~/.copilot/session-state/{id}/events.jsonl — token 用量（session.shutdown → modelMetrics）
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai_spend_tracker.collectors.base import BaseCollector
from ai_spend_tracker.config import get_path_override
from ai_spend_tracker.models import SessionRecord


def _find_windows_copilot_db() -> Path | None:
    """从 WSL 内查找 Windows 侧的 Copilot session-store.db。"""
    mnt_users = Path("/mnt/c/Users")
    if not mnt_users.exists():
        return None
    wsl_user = os.environ.get("USER", "")
    if wsl_user:
        p = mnt_users / wsl_user / ".copilot" / "session-store.db"
        try:
            if p.exists():
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
    for c in candidates:
        p = c / ".copilot" / "session-store.db"
        try:
            if p.exists():
                return p
        except PermissionError:
            continue
    return None


def copilot_session_db_path() -> Path | None:
    """查找 Copilot CLI session-store.db 的路径。"""
    # 1. 用户手动覆盖
    override = get_path_override("copilot")
    if override:
        return override

    # 2. Linux / macOS
    default_path = Path.home() / ".copilot" / "session-store.db"
    if default_path.exists():
        return default_path

    # 3. macOS（~/Library/Application Support/ 备用）
    mac_path = (
        Path.home() / "Library" / "Application Support" / "copilot" / "session-store.db"
    )
    if mac_path.exists():
        return mac_path

    # 4. Windows 原生路径（通过 /mnt/c/ 访问）
    win_path = _find_windows_copilot_db()
    if win_path:
        return win_path

    return None


def _parse_events_jsonl(events_path: Path) -> dict:
    """解析 events.jsonl，提取 session.shutdown 中的 modelMetrics。"""
    try:
        with open(events_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "session.shutdown":
                    data = event.get("data", {})
                    model_metrics = data.get("modelMetrics", {})
                    if model_metrics:
                        return model_metrics
        # 没找到 shutdown 事件（session 可能还在进行中）
        return {}
    except (FileNotFoundError, PermissionError):
        return {}
    except Exception:
        return {}


class CopilotCollector(BaseCollector):
    """采集 GitHub Copilot CLI 的 token 用量数据。"""

    def name(self) -> str:
        return "copilot"

    def display_name(self) -> str:
        return "GitHub Copilot CLI"

    def description(self) -> str:
        return "GitHub Copilot CLI — local sessions via session-store.db + events.jsonl"

    def collect(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[SessionRecord]:
        db_path = copilot_session_db_path()
        if db_path is None or not db_path.exists():
            return []

        session_state_dir = db_path.parent / "session-state"

        records: list[SessionRecord] = []

        # 先读 DB（可能被 Copilot 锁定，复制到临时文件）
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        try:
            import shutil
            shutil.copy2(str(db_path), tmp.name)
            tmp.close()

            conn = sqlite3.connect(f"file:{tmp.name}?mode=ro", uri=True)
            try:
                cur = conn.cursor()

                # 查询 sessions 表（列名来源于 copilot-cli 源码和社区实践）
                rows = cur.execute(
                    "SELECT id, created_at, updated_at, summary, repository FROM sessions"
                ).fetchall()

                for sid, created_ts, updated_ts, summary, repository in rows:
                    # 时间过滤
                    started_at = (
                        datetime.fromtimestamp(created_ts / 1000, tz=timezone.utc)
                        if created_ts else None
                    )
                    ended_at = (
                        datetime.fromtimestamp(updated_ts / 1000, tz=timezone.utc)
                        if updated_ts else None
                    )

                    if since and (started_at is None or started_at < since):
                        continue
                    if until and (started_at is not None and started_at > until):
                        continue

                    # 读 events.jsonl 拿 token 用量
                    events_path = session_state_dir / sid / "events.jsonl"
                    model_metrics = _parse_events_jsonl(events_path)

                    if not model_metrics:
                        # 没有 shutdown 事件，可能 session 还在运行，跳过
                        continue

                    total_in = 0
                    total_out = 0
                    total_cache_read = 0
                    total_cache_write = 0
                    total_cost = 0.0
                    models_used: list[str] = []

                    for model_name, metrics in model_metrics.items():
                        usage = metrics.get("usage", {}) if isinstance(metrics, dict) else {}
                        if isinstance(usage, dict):
                            inp = usage.get("input_tokens") or usage.get("inputTokens") or 0
                            out = usage.get("output_tokens") or usage.get("outputTokens") or 0
                            cache_r = usage.get("cache_read_input_tokens") or usage.get("cacheReadInputTokens") or 0
                            cache_w = usage.get("cache_creation_input_tokens") or usage.get("cacheCreationInputTokens") or 0
                        else:
                            inp = out = cache_r = cache_w = 0

                        total_in += inp
                        total_out += out
                        total_cache_read += cache_r
                        total_cache_write += cache_w

                        # 按 model 估算费用
                        from ai_spend_tracker.collectors.base import estimate_cost
                        cost = estimate_cost(
                            input_tokens=inp,
                            output_tokens=out,
                            model=model_name,
                        )
                        total_cost += cost
                        models_used.append(model_name)

                    records.append(
                        SessionRecord(
                            session_id=sid,
                            source=self.name(),
                            model=",".join(sorted(set(models_used))) if models_used else "unknown",
                            started_at=started_at,
                            ended_at=ended_at,
                            input_tokens=total_in,
                            output_tokens=total_out,
                            cache_read_tokens=total_cache_read,
                            cache_write_tokens=total_cache_write,
                            cost_usd=round(total_cost, 6),
                            api_calls=1,
                        )
                    )
            finally:
                conn.close()
        except Exception:
            return []
        finally:
            Path(tmp.name).unlink(missing_ok=True)

        return records
