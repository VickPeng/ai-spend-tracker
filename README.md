# AI Spend Tracker

**Aggregate token usage & cost across all your AI coding agents in one CLI.**

Hermes Agent, Codex CLI, Claude Code, Cursor, OpenClaw — if you run multiple AI coding tools, you're probably flying blind on how much you're actually spending. AI Spend Tracker pulls session data from every agent you use and shows you the big picture.

## Features

- **Multi-agent aggregation** — see Hermes + Codex + custom agents in one report
- **Built-in collectors** — works out of the box with Hermes Agent and Codex CLI
- **Extensible** — add custom collectors for any AI agent
- **Plug-in architecture** — drop a Python file in `~/.ai-spend/collectors/`, it just works
- **Rich terminal output** — agent summary, model breakdown, daily trends
- **JSON output** — pipe data into your own dashboards

## Quick Start

```bash
# Install
pip install ai-spend-tracker

# See your usage for the last 7 days
ai-spend

# List available data sources
ai-spend --list-agents
```

## Usage

```bash
# Default: last 7 days
ai-spend

# Custom time range
ai-spend --days 30
ai-spend --since 2026-01-01 --until 2026-06-01
ai-spend --days 0              # all time

# Filter by agent
ai-spend --agent hermes
ai-spend --agent hermes,codex

# JSON output (great for piping)
ai-spend --format json

# Initialize custom collector directory
ai-spend init
# Or create a named collector:
ai-spend init my-custom-agent

# List available collectors
ai-spend --list-agents
```

## Supported Agents

| Agent | Status | Data Source |
|-------|--------|-------------|
| Hermes Agent | ✅ Built-in | `~/.hermes/state.db` |
| Codex CLI | ✅ Built-in | `~/.codex/state_N.sqlite` |
| Claude Code | 🔄 In progress | Hook-based (see roadmap) |
| OpenClaw | 🔄 Planned | TBD |
| Your custom agent | ✅ Via plugin | `~/.ai-spend/collectors/your_agent.py` |

## Custom Collectors

Any AI agent can be tracked by writing a 20-line Python file:

```python
# ~/.ai-spend/collectors/my-agent.py
from ai_spend_tracker.collectors.base import BaseCollector, estimate_cost
from ai_spend_tracker.models import SessionRecord

class MyAgentCollector(BaseCollector):
    def name(self) -> str:
        return "my-agent"

    def display_name(self) -> str:
        return "My Agent"

    def collect(self, since=None, until=None):
        # Read your agent's logs, parse them, return SessionRecord[]
        return [
            SessionRecord(
                session_id="...",
                source=self.name(),
                model="gpt-4",
                input_tokens=1000,
                output_tokens=200,
                cost_usd=estimate_cost(1000, 200, "gpt-4"),
            )
        ]
```

Run `ai-spend init <name>` to generate a template.

## Roadmap

- **Phase 1** (current): CLI tool — local aggregation across installed agents
- **Phase 2**: Web dashboard — cloud panel with history & trends
- **Phase 3**: Pro — proxy mode for precise tracking, team features, alerts

## License

MIT
