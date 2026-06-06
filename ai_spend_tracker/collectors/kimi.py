"""
KimiCollector — 从 Kimi Code CLI 的 wire.jsonl 日志读取用量数据。

数据位置：
  ~/.kimi/sessions/<group-id>/<session-id>/wire.jsonl（默认）
  或 $KIMI_DATA_DIR/sessions/<group-id>/<session-id>/wire.jsonl

wire.jsonl 中的 StatusUpdate 事件包含 token_usage：
  {
    "type": "StatusUpdate",
    "token_usage": {
      "input_other": 1234,         // input tokens
      "output": 567,               // output tokens
      "input_cache_read": 890,     // cache read tokens
      "input_cache_creation": 12   // cache write tokens
    }
  }

参考：
  - ccusage: https://ccusage.com/guide/kimi
  - Kimi CLI: https://github.com/MoonshotAI/kimi-cli
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai_spend_tracker.collectors.base import BaseCollector, estimate_cost
from ai_spend_tracker.config import get_path_override
from ai_spend_tracker.models import SessionRecord


def _find_kimi_root() -> Path | None:
    """查找 Kimi Code CLI 的数据根目录。"""
    # 0. 环境变量 $KIMI_DATA_DIR
    env_dir = os.environ.get("KIMI_DATA_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            return p

    # 1. 用户手动覆盖
    override = get_path_override("kimi")
    if override:
        if override.is_dir():
            if (override / "sessions").is_dir():
                return override
            return override.parent
        return override.parent if override.suffix == ".jsonl" else None

    # 2. Linux / macOS 默认
    default_path = Path.home() / ".kimi"
    if default_path.is_dir():
        return default_path

    # 3. macOS（~/Library/Application Support/ 备用）
    mac_path = Path.home() / "Library" / "Application Support" / "kimi"
    if mac_path.is_dir():
        return mac_path

    # 4. Windows（通过 WSL /mnt/c/）
    mnt_users = Path("/mnt/c/Users")
    if mnt_users.exists():
        wsl_user = os.environ.get("USER", "")
        try:
            for base_dir in [mnt_users / wsl_user] if wsl_user else []:
                for candidate in [
                    base_dir / ".kimi",
                    base_dir / "AppData" / "Local" / "kimi",
                ]:
                    try:
                        if candidate.is_dir():
                            return candidate
                    except PermissionError:
                        continue
        except Exception:
            pass

    return None


def _parse_timestamp(ts: str | int | float | None) -> datetime | None:
    """解析 Kimi 的时间戳（ISO 字符串或毫秒时间戳）。"""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass
    return None


class KimiCollector(BaseCollector):
    """采集 Kimi Code CLI 的 token 用量数据。"""

    def name(self) -> str:
        return "kimi"

    def display_name(self) -> str:
        return "Kimi Code CLI"

    def description(self) -> str:
        return (
            "Kimi Code CLI (Moonshot AI) — wire.jsonl logs in ~/.kimi/"
        )

    def collect(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[SessionRecord]:
        root = _find_kimi_root()
        if root is None:
            return []

        sessions_dir = root / "sessions"
        if not sessions_dir.is_dir():
            return []

        records: list[SessionRecord] = []

        # 遍历 group 目录
        for group_dir in sorted(sessions_dir.iterdir()):
            if not group_dir.is_dir() or group_dir.name.startswith("."):
                continue

            # 遍历 session 目录
            for session_dir in sorted(group_dir.iterdir()):
                if not session_dir.is_dir() or session_dir.name.startswith("."):
                    continue

                wire_file = session_dir / "wire.jsonl"
                if not wire_file.is_file():
                    continue

                session_id = session_dir.name
                session_start: Optional[datetime] = None
                session_end: Optional[datetime] = None
                models: set[str] = set()
                total_input = 0
                total_output = 0
                total_cache_read = 0
                total_cache_write = 0
                assistant_msg_count = 0

                try:
                    with open(wire_file, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                entry = json.loads(line)
                            except json.JSONDecodeError:
                                continue

                            entry_type = entry.get("type", "")

                            # 时间戳
                            ts = _parse_timestamp(entry.get("timestamp"))
                            if ts:
                                if session_start is None or ts < session_start:
                                    session_start = ts
                                if session_end is None or ts > session_end:
                                    session_end = ts

                            # 从 StatusUpdate 中提取 token 用量
                            if entry_type == "StatusUpdate":
                                usage = entry.get("token_usage")
                                if not usage or not isinstance(usage, dict):
                                    continue
                                inp = usage.get("input_other", 0) or 0
                                out = usage.get("output", 0) or 0
                                cache_r = usage.get("input_cache_read", 0) or 0
                                cache_w = usage.get("input_cache_creation", 0) or 0

                                if inp > 0 or out > 0:
                                    total_input += inp
                                    total_output += out
                                    total_cache_read += cache_r
                                    total_cache_write += cache_w
                                    assistant_msg_count += 1

                                    # 模型名：从 entry 中提取或使用默认
                                    model = (entry.get("model") or "kimi-for-coding").strip()
                                    models.add(model)

                except (OSError, PermissionError):
                    continue

                if assistant_msg_count == 0:
                    continue

                if since and session_start and session_start < since:
                    continue
                if until and session_start and session_start > until:
                    continue

                # 计算费用
                model_str = ",".join(sorted(models)) if models else "kimi-for-coding"
                total_cost = 0.0
                for model_name in models:
                    cost = estimate_cost(
                        input_tokens=total_input,
                        output_tokens=total_output,
                        model=model_name,
                    )
                    total_cost += cost / len(models)

                records.append(
                    SessionRecord(
                        session_id=f"{group_dir.name}/{session_id}",
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

        return records
