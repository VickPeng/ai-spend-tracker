"""
HermesCollector — 从 Hermes Agent 的 state.db 读取会话数据。
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai_spend_tracker.collectors.base import BaseCollector
from ai_spend_tracker.config import hermes_db_path
from ai_spend_tracker.models import SessionRecord


class HermesCollector(BaseCollector):
    """采集 Hermes Agent 的 token 用量数据。"""

    def name(self) -> str:
        return "hermes"

    def display_name(self) -> str:
        return "Hermes Agent"

    def description(self) -> str:
        return "Hermes Agent — CLI & cron sessions via state.db"

    def _db_path(self) -> Path | None:
        return hermes_db_path()

    def collect(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[SessionRecord]:
        db_path = self._db_path()
        if db_path is None or not db_path.exists():
            return []

        # Hermes 可能正在运行（DB 被锁），复制到临时文件再读
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        try:
            shutil.copy2(str(db_path), tmp.name)
            tmp.close()
            return self._read_db(tmp.name, since, until)
        except Exception:
            return []
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def _read_db(
        self,
        db_path: str,
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> list[SessionRecord]:
        records: list[SessionRecord] = []
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = conn.cursor()

            # 构建 SQL
            conditions: list[str] = []
            params: list[float] = []
            if since is not None:
                conditions.append("started_at >= ?")
                params.append(since.timestamp())
            if until is not None:
                conditions.append("started_at <= ?")
                params.append(until.timestamp())

            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)

            query = f"""
                SELECT id, source, model, started_at, ended_at,
                       message_count, tool_call_count,
                       input_tokens, output_tokens,
                       cache_read_tokens, cache_write_tokens,
                       reasoning_tokens, estimated_cost_usd, api_call_count
                FROM sessions
                {where_clause}
                ORDER BY started_at DESC
            """
            cur.execute(query, params)

            for row in cur.fetchall():
                (
                    sid, source, model, started_ts, ended_ts,
                    msg_count, tool_count,
                    inp, out, cache_r, cache_w, reason,
                    cost, api_calls,
                ) = row

                records.append(
                    SessionRecord(
                        session_id=sid,
                        source=self.name(),
                        model=model or "unknown",
                        started_at=(
                            datetime.fromtimestamp(started_ts, tz=timezone.utc)
                            if started_ts else None
                        ),
                        ended_at=(
                            datetime.fromtimestamp(ended_ts, tz=timezone.utc)
                            if ended_ts else None
                        ),
                        input_tokens=inp or 0,
                        output_tokens=out or 0,
                        cache_read_tokens=cache_r or 0,
                        cache_write_tokens=cache_w or 0,
                        reasoning_tokens=reason or 0,
                        cost_usd=cost or 0.0,
                        api_calls=api_calls or 1,
                    )
                )
        finally:
            conn.close()

        return records
