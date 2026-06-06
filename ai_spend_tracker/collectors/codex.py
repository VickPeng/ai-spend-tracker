"""
CodexCollector — 从 OpenAI Codex CLI 的 state 数据库读取会话数据。

数据来源：Windows ~/.codex/state_N.sqlite（通过 /mnt/c/ 路径访问）
注意：tokens_used 是总 token 数（未区分 input/output），
      费用按 4:1 的 input/output 比例估算。
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ai_spend_tracker.collectors.base import BaseCollector, estimate_cost
from ai_spend_tracker.config import codex_state_db_path
from ai_spend_tracker.models import SessionRecord


class CodexCollector(BaseCollector):
    """采集 OpenAI Codex CLI 的 token 用量数据。"""

    def name(self) -> str:
        return "codex"

    def display_name(self) -> str:
        return "Codex CLI"

    def description(self) -> str:
        return "OpenAI Codex CLI — coding sessions via state.sqlite"

    def _db_path(self) -> Path | None:
        return codex_state_db_path()

    def collect(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[SessionRecord]:
        db_path = self._db_path()
        if db_path is None or not db_path.exists():
            return []

        # Codex 可能正在运行（DB 被锁），复制后再读
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
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

            conditions: list[str] = []
            params: list = []
            if since is not None:
                conditions.append("created_at >= ?")
                params.append(int(since.timestamp()))
            if until is not None:
                conditions.append("created_at <= ?")
                params.append(int(until.timestamp()))

            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)

            query = f"""
                SELECT id, title, created_at, updated_at,
                       model_provider, model, tokens_used
                FROM threads
                {where_clause}
                ORDER BY created_at DESC
            """
            cur.execute(query, params)

            for row in cur.fetchall():
                sid, title, created_ts, updated_ts, provider, model, tokens = row

                # tokens_used 是总 token，按 4:1 估算 input/output
                total_tokens = tokens or 0
                estimated_input = int(total_tokens * 0.8)
                estimated_output = total_tokens - estimated_input

                # 估算费用
                cost = estimate_cost(
                    input_tokens=estimated_input,
                    output_tokens=estimated_output,
                    model=model or provider or "unknown",
                )

                records.append(
                    SessionRecord(
                        session_id=sid,
                        source=self.name(),
                        model=model or provider or "unknown",
                        started_at=(
                            datetime.fromtimestamp(created_ts, tz=timezone.utc)
                            if created_ts else None
                        ),
                        ended_at=(
                            datetime.fromtimestamp(updated_ts, tz=timezone.utc)
                            if updated_ts else None
                        ),
                        input_tokens=estimated_input,
                        output_tokens=estimated_output,
                        cost_usd=cost,
                        api_calls=1,
                    )
                )
        finally:
            conn.close()

        return records
