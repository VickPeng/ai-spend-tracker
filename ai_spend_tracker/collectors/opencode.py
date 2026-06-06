"""
OpenCodeCollector — 从 OpenCode CLI 的 SQLite 数据库读取用量数据。

数据来源：
  ~/.local/share/opencode/opencode.db（Linux / WSL）
  %APPDATA%/opencode/opencode.db（Windows）

表结构：
  session — id, parent_id, title, time_created, time_updated, project_id
  project — id, name, worktree
  message — session_id, data (JSON), time_created
  message.data 的 JSON 包含 tokens, modelID, providerID, cost 等字段
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai_spend_tracker.collectors.base import BaseCollector, estimate_cost
from ai_spend_tracker.config import get_path_override
from ai_spend_tracker.models import SessionRecord


def _find_windows_opencode_db() -> Path | None:
    """从 WSL 内查找 Windows 侧的 opencode.db。"""
    mnt_users = Path("/mnt/c/Users")
    if not mnt_users.exists():
        return None
    wsl_user = os.environ.get("USER", "")
    if wsl_user:
        p = mnt_users / wsl_user / "AppData" / "Roaming" / "opencode" / "opencode.db"
        try:
            if p.exists():
                return p
        except PermissionError:
            pass
    # fallback：遍历其他用户目录
    try:
        candidates = sorted(
            [c for c in mnt_users.iterdir() if c.is_dir() and not c.name.startswith(".")],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
    except PermissionError:
        candidates = []
    for base in candidates:
        p = base / "AppData" / "Roaming" / "opencode" / "opencode.db"
        try:
            if p.exists():
                return p
        except PermissionError:
            continue
    return None


def opencode_db_path() -> Path | None:
    """查找 OpenCode 的 SQLite 数据库路径。"""
    # 1. 用户手动覆盖
    override = get_path_override("opencode")
    if override:
        return override

    # 2. Linux / WSL 路径
    linux_path = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    if linux_path.exists():
        return linux_path

    # 3. macOS 路径
    mac_path = Path.home() / "Library" / "Application Support" / "opencode" / "opencode.db"
    if mac_path.exists():
        return mac_path

    # 4. Windows 路径（通过 WSL /mnt/c/）
    win_path = _find_windows_opencode_db()
    if win_path:
        return win_path

    return None


class OpenCodeCollector(BaseCollector):
    """采集 OpenCode CLI 的 token 用量数据。"""

    def name(self) -> str:
        return "opencode"

    def display_name(self) -> str:
        return "OpenCode CLI"

    def description(self) -> str:
        return "OpenCode CLI — SQLite database with per-message token usage"

    def collect(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[SessionRecord]:
        db_path = opencode_db_path()
        if db_path is None or not db_path.exists():
            return []

        # OpenCode 可能正在运行，复制到临时文件
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        try:
            import shutil
            shutil.copy2(str(db_path), tmp.name)
            tmp.close()

            conn = sqlite3.connect(f"file:{tmp.name}?mode=ro", uri=True)
            try:
                return self._read_db(conn, since, until)
            finally:
                conn.close()
        except Exception:
            return []
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def _read_db(
        self,
        conn: sqlite3.Connection,
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> list[SessionRecord]:
        # 收集 session 元数据
        session_map: dict[str, dict] = {}
        try:
            rows = conn.execute(
                "SELECT id, parent_id, title, time_created, time_updated "
                "FROM session ORDER BY time_created DESC"
            ).fetchall()
            for sid, parent_id, title, created_ts, updated_ts in rows:
                started_at = (
                    datetime.fromtimestamp(created_ts / 1000, tz=timezone.utc)
                    if created_ts else None
                )
                ended_at = (
                    datetime.fromtimestamp(updated_ts / 1000, tz=timezone.utc)
                    if updated_ts else None
                )
                session_map[sid] = {
                    "parent_id": parent_id,
                    "title": title or sid[:8],
                    "started_at": started_at,
                    "ended_at": ended_at,
                }
        except Exception:
            pass

        if not session_map:
            return []

        # 读取所有 message，汇总每 session 的 token 用量
        session_usage: dict[str, dict] = {}

        try:
            msg_rows = conn.execute(
                "SELECT session_id, data, time_created FROM message "
                "ORDER BY session_id ASC, time_created ASC"
            ).fetchall()
        except Exception:
            msg_rows = []

        for msg_sid, raw_data, _ in msg_rows:
            if msg_sid not in session_map:
                continue

            # 过滤时间
            session_info = session_map[msg_sid]
            started_at = session_info["started_at"]
            if since and (started_at is None or started_at < since):
                continue
            if until and (started_at is not None and started_at > until):
                continue

            # 解析 message.data JSON
            if not raw_data or not isinstance(raw_data, str):
                continue
            try:
                msg = json.loads(raw_data)
            except json.JSONDecodeError:
                continue

            role = (msg.get("role") or "").strip().lower()
            if role != "assistant":
                continue

            tokens = msg.get("tokens", {})
            if not isinstance(tokens, dict):
                continue

            inp = tokens.get("input", 0) or 0
            out = tokens.get("output", 0) or 0
            cache = tokens.get("cache", {}) or {}
            cache_r = cache.get("read", 0) or 0
            cache_w = cache.get("write", 0) or 0

            model_id = (msg.get("modelID") or msg.get("model") or "unknown").strip()
            provider_id = (msg.get("providerID") or "").strip()
            full_model = f"{provider_id}/{model_id}" if provider_id else model_id

            if msg_sid not in session_usage:
                session_usage[msg_sid] = {
                    "models": set(),
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "cost_usd": 0.0,
                    "api_calls": 0,
                }

            usage = session_usage[msg_sid]
            usage["models"].add(full_model)
            usage["input_tokens"] += inp
            usage["output_tokens"] += out
            usage["cache_read_tokens"] += cache_r
            usage["cache_write_tokens"] += cache_w
            usage["cost_usd"] += estimate_cost(
                input_tokens=inp,
                output_tokens=out,
                model=full_model,
            )
            usage["api_calls"] += 1

        # 组装结果
        records: list[SessionRecord] = []
        for sid, usage in session_usage.items():
            session_info = session_map.get(sid, {})
            models_str = ",".join(sorted(usage["models"])) if usage["models"] else "unknown"
            records.append(
                SessionRecord(
                    session_id=sid,
                    source=self.name(),
                    model=models_str,
                    started_at=session_info.get("started_at"),
                    ended_at=session_info.get("ended_at"),
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cache_read_tokens=usage["cache_read_tokens"],
                    cache_write_tokens=usage["cache_write_tokens"],
                    cost_usd=round(usage["cost_usd"], 6),
                    api_calls=usage["api_calls"],
                )
            )

        return records
