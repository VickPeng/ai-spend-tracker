"""
OpenClawCollector — 从 OpenClaw 的 JSONL 会话日志读取用量数据。

数据位置：~/.openclaw/agents/<agent-name>/sessions/<session-id>.jsonl

JSONL 中 message.usage 结构：
  {
    "input": 17637,
    "output": 162,
    "cacheRead": 0,
    "cacheWrite": 0,
    "reasoningTokens": 49,
    "totalTokens": 17799,
    "cost": {
      "input": 0.00246918,
      "output": 4.536e-05,
      "cacheRead": 0,
      "cacheWrite": 0,
      "total": 0.00251454
    }
  }

费用已经在 usage.cost.total 中预计算好了，直接读取即可。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai_spend_tracker.collectors.base import BaseCollector
from ai_spend_tracker.config import get_path_override
from ai_spend_tracker.models import SessionRecord


# OpenClaw 数据根目录
OPENCLAW_DIRNAME = ".openclaw"


def _find_openclaw_root() -> Path | None:
    """查找 OpenClaw 数据根目录。"""
    # 1. 手动覆盖
    override = get_path_override("openclaw")
    if override:
        if override.is_dir():
            # 可能是 agents/ 目录或根目录
            if (override / "agents").is_dir():
                return override
            return override.parent
        return override.parent if override.suffix == ".jsonl" else None

    # 2. Linux / macOS
    default_path = Path.home() / OPENCLAW_DIRNAME
    if default_path.is_dir():
        return default_path

    # 3. macOS（~/Library/Application Support/ 备用）
    mac_path = Path.home() / "Library" / "Application Support" / "openclaw"
    if mac_path.is_dir():
        return mac_path

    # 4. Windows（通过 /mnt/c/）
    wsl_user = os.environ.get("USER", "")
    if wsl_user:
        p = Path("/mnt/c/Users") / wsl_user / OPENCLAW_DIRNAME
        try:
            if p.is_dir():
                return p
        except PermissionError:
            pass
    # fallback：遍历用户目录
    mnt_users = Path("/mnt/c/Users")
    if mnt_users.exists():
        try:
            for base in sorted(mnt_users.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if base.is_dir() and not base.name.startswith("."):
                    p = base / OPENCLAW_DIRNAME
                    try:
                        if p.is_dir():
                            return p
                    except PermissionError:
                        continue
        except PermissionError:
            pass

    return None


def _parse_timestamp(ts: int | str | None) -> datetime | None:
    """解析 OpenClaw 的时间戳（毫秒时间戳或 ISO 字符串）。"""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass
    return None


class OpenClawCollector(BaseCollector):
    """采集 OpenClaw 的 token 用量数据。"""

    def name(self) -> str:
        return "openclaw"

    def display_name(self) -> str:
        return "OpenClaw"

    def description(self) -> str:
        return "OpenClaw — JSONL session logs with pre-calculated costs"

    def collect(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[SessionRecord]:
        root = _find_openclaw_root()
        if root is None:
            return []

        agents_dir = root / "agents"
        if not agents_dir.is_dir():
            return []

        records: list[SessionRecord] = []

        for agent_dir in sorted(agents_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name.startswith("."):
                continue
            agent_name = agent_dir.name

            sessions_dir = agent_dir / "sessions"
            if not sessions_dir.is_dir():
                continue

            # 遍历 JSONL 文件
            for jsonl_file in sorted(sessions_dir.glob("*.jsonl")):
                if not jsonl_file.is_file() or ".trajectory" in jsonl_file.name:
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
                has_precalculated_cost = False

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
                            msg = entry.get("message") or {}

                            # 时间戳
                            ts = _parse_timestamp(entry.get("timestamp"))
                            if ts:
                                if session_start is None or ts < session_start:
                                    session_start = ts
                                if session_end is None or ts > session_end:
                                    session_end = ts

                            if entry_type == "session":
                                # session 记录可能携带全局时间
                                ts2 = _parse_timestamp(entry.get("timestamp"))
                                if ts2:
                                    if session_start is None or ts2 < session_start:
                                        session_start = ts2
                                    if session_end is None or ts2 > session_end:
                                        session_end = ts2

                            if entry_type == "message" and msg.get("role") == "assistant":
                                usage = msg.get("usage") or {}
                                model = (msg.get("model") or msg.get("modelId") or "").strip()
                                provider = (msg.get("provider") or "").strip()
                                full_model = f"{provider}/{model}" if provider and model else model or "unknown"
                                models.add(full_model)

                                inp = usage.get("input", 0) or 0
                                out = usage.get("output", 0) or 0
                                cache_r = usage.get("cacheRead", 0) or 0
                                cache_w = usage.get("cacheWrite", 0) or 0

                                total_input += inp
                                total_output += out
                                total_cache_read += cache_r
                                total_cache_write += cache_w
                                assistant_msg_count += 1

                                # 使用预计算费用（如果有）
                                cost_info = usage.get("cost") or {}
                                if isinstance(cost_info, dict):
                                    msg_cost = cost_info.get("total", 0) or 0
                                    if msg_cost:
                                        total_cost += msg_cost
                                        has_precalculated_cost = True

                except (OSError, PermissionError):
                    continue

                if assistant_msg_count == 0:
                    continue

                if since and session_start and session_start < since:
                    continue
                if until and session_start and session_start > until:
                    continue

                # 如果没有预计算费用，从定价表估算
                if not has_precalculated_cost:
                    from ai_spend_tracker.collectors.base import estimate_cost
                    cost_sum = 0.0
                    for model_name in models:
                        cost_sum += estimate_cost(
                            input_tokens=total_input,
                            output_tokens=total_output,
                            model=model_name,
                        ) / len(models)
                    total_cost = round(cost_sum, 6)

                records.append(
                    SessionRecord(
                        session_id=session_id,
                        source=self.name(),
                        model=",".join(sorted(models)) if models else "unknown",
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
