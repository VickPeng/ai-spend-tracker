# AI Spend Tracker — Phase 1 实现方案

> 项目路径：`D:\acode\ai-spend-tracker\`（WSL2: `/mnt/d/acode/ai-spend-tracker/`）

---

## 一、Phase 1 边界

**只做一件事：**
1. 自动发现所有支持的 agent 数据源 → 终端上以表格 + 汇总展示 token 用量和费用

**不做（留给 Phase 2/3）：**
- Web UI
- 数据上传 / 云端同步
- 告警 / 预算
- 多用户 / 团队功能
- 复杂的前端交互

**必须从一开始就做对的事：**
- Collector 架构要做到加一个新 agent = 放一个 `.py` 文件，零行框架代码改动
- 所有代码**不能写死具体哪个 agent**，包括路径、显示、过滤逻辑

---

## 二、架构设计

### 核心原则：插件式 Collector + 用户自定义扩展

```
                           内置 Collector（开箱即用）
                          ┌── hermes.py ──→ Hermes state.db (WSL2)
                          ├── codex.py ───→ Codex state_5.sqlite (Win)
main.py ──→ CollectorRegistry ──┼── claude.py ─→ Claude Code (待调研)
           (自动发现)         ├── openclaw.py → OpenClaw (待调研)
                              ├── cursor.py ──→ Cursor (待调研)
                              └── ...更多知名 agent
                                       │
                           自定义 Collector（用户编写）
                          ┌── .ai-spend/collectors/my_agent.py
                          │   用户只需实现：
                          │   1. collect() → 返回 SessionRecord[]
                          │   2. pricing() → {model: price_per_token}
                          │   3. 框架提供：SQLite/JSON/CSV 读取工具函数
                          └── .ai-spend/collectors/custom_api.py
                                       │
                                       ↓
                               SessionRecord（统一模型）
                                       │
                                       ↓
                               AggregatedStats（聚合统计）
                                       │
                                       ↓
                               Display（rich 表格）
```

**产品定位：做 AI agent 用量追踪的"标准层"**

- **内置支持**：覆盖主流 agent，用户安装后直接能用
- **自定义扩展**：用户写一个 Python 文件继承基类，就能追踪任意 agent，包括：
  - 公司内部的私有 agent
  - 老板不问世的 side project agent
  - 未来还没出现的 agent
- **社区共享**：自定义 collector 可以提交 PR 变为内置

**加一个新 agent（内置）需要三步：**
1. 在 `src/collectors/` 下新建一个 `.py` 文件
2. 继承 `BaseCollector`，实现 `collect()` + `name()` + `pricing_table()`
3. 在 `collectors/__init__.py` 里注册

**用户自定义只需要两步：**
1. 在 `~/.ai-spend/collectors/` 下新建一个 `.py` 文件
2. 继承 `BaseCollector` 实现接口

### 目录结构

```
D:\acode\ai-spend-tracker\
├── pyproject.toml           # 项目配置 + 依赖
├── README.md                # 使用说明（先写英文）
├── src/
│   ├── __init__.py
│   ├── main.py              # CLI 入口（argparse）
│   ├── models.py            # SessionRecord / AggregatedStats 数据模型
│   ├── collectors/
│   │   ├── __init__.py      # CollectorRegistry（内置 + 用户自定义自动发现）
│   │   ├── base.py          # BaseCollector 抽象接口
│   │   ├── hermes.py        # HermesCollector（内置）
│   │   ├── codex.py         # CodexCollector（内置）
│   │   ├── ...              # 更多内置 collector
│   ├── display.py           # 终端输出（rich 表格）
│   └── config.py            # 路径配置 + 自动检测

~/.ai-spend/                  # 用户自定义目录（自动创建）
└── collectors/               # 用户放自定义 collector 的地方
    └── my_agent.py           # 继承 BaseCollector 即可
```

### 对外命令

```
# 查看所有会话摘要（默认最近 7 天）
ai-spend

# 按 agent 筛选（collector name）
ai-spend --agent hermes
ai-spend --agent codex
ai-spend --agent hermes,codex

# 列出所有可用的 agent
ai-spend --list-agents

# 自定义时间范围
ai-spend --days 30
ai-spend --since 2026-01-01 --until 2026-06-01

# JSON 格式输出（给管道用）
ai-spend --format json

# 启动交互式 TUI（可选，MVP 可先不做）
ai-spend --tui
```

---

## 三、数据模型

### Hermes state.db sessions 表
```
id, source, model, started_at, ended_at
message_count, tool_call_count
input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, reasoning_tokens
estimated_cost_usd, actual_cost_usd, billing_provider
```

### Codex state_5.sqlite threads 表
```
id, title, created_at, updated_at
model_provider, tokens_used, model
```

### 统一模型（src/models.py）

```python
@dataclass
class SessionRecord:
    session_id: str
    source: str           # "hermes" | "codex"
    model: str
    started_at: datetime
    ended_at: datetime | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    api_calls: int = 0

@dataclass
class AggregatedStats:
    total_sessions: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read: int
    total_cache_write: int
    total_reasoning_tokens: int
    total_cost_usd: float
    total_api_calls: int
    by_tool: dict[str, 'AggregatedStats']  # 按工具细分
    by_model: dict[str, 'AggregatedStats']  # 按模型细分
    daily: list[tuple[str, 'AggregatedStats']]  # 每日趋势
```

---

## 四、Collector 接口

```python
# src/collectors/base.py
class BaseCollector(ABC):
    @abstractmethod
    def collect(self, since: datetime | None, until: datetime | None) -> list[SessionRecord]:
        """读取数据源，返回统一格式的 SessionRecord 列表"""
        pass

    @abstractmethod
    def name(self) -> str:
        """返回数据源名称，如 'hermes' / 'codex'"""
        pass
```

---

## 五、终端输出设计（display.py）

使用 `rich` 库，包含三个区块：

```
╔══════════════════════════════════════════════╗
║     AI Spend Tracker — 用量汇总             ║
║     2026-06-01 ~ 2026-06-06                 ║
║     检测到 2/4 个 agent 有数据              ║
╚══════════════════════════════════════════════╝

 Agent     会话数   输入token    输出token    费用(USD)
 ──────── ──────── ─────────── ─────────── ───────────
 hermes       42     125,340      18,230      $0.48
 codex        18      95,100      12,450      $0.31
 ──────── ──────── ─────────── ─────────── ───────────
 合计         60     220,440      30,680      $0.79

 模型明细：
 模型              输入token    输出token    费用
 ──────────────── ─────────── ─────────── ──────
 deepseek-v4-pro     85,200      12,100    $0.35
 deepseek-v4-flash   40,140       6,130    $0.13
 qwen3.7-max         95,100      12,450    $0.31

 每日趋势：
 日期        会话   token总量    费用
 ────────── ──── ────────── ──────
 06-01(一)    8     32,100    $0.11
 06-02(二)   12     51,200    $0.18
 06-03(三)   10     38,900    $0.14
 ...
```

**Agent 列不能写死。** 有多少个 agent 检测到就显示多少行。名称来自 `Collector.name()`。

---

## 六、文件清单（按实现顺序）

| 序号 | 文件 | 内容 | 行数估计 |
|------|------|------|---------|
| 1 | `pyproject.toml` | 项目元数据 + 依赖（rich + click） | ~25 |
| 2 | `src/models.py` | SessionRecord + AggregatedStats | ~60 |
| 3 | `src/collectors/base.py` | BaseCollector 抽象类 | ~15 |
| 4 | `src/config.py` | 默认路径检测 + 自动查找 | ~40 |
| 5 | `src/collectors/hermes.py` | 读 Hermes state.db | ~50 |
| 6 | `src/collectors/codex.py` | 读 Codex state_5.sqlite（/mnt/c/） | ~50 |
| 7 | `src/display.py` | rich 表格渲染 | ~80 |
| 8 | `src/main.py` | CLI 入口 + 聚合逻辑 | ~100 |
| 9 | `README.md` | 英文使用说明 | ~80 |

---

## 七、关键设计决策

### 1. 命令行解析用 `argparse` 还是 `click`？
- ✅ 用 `argparse`（Python 内置，无需额外依赖）
- `click` 虽然好用但要多一个依赖，MVP 不必要

### 2. Hermes DB 路径自动检测
```
~/.hermes/state.db          # WSL2 默认
/mnt/c/Users/13018/.hermes/state.db  # Windows Hermes（可选）
```

### 3. Codex DB 路径
```
/mnt/c/Users/13018/.codex/state_5.sqlite
```
注意：`.codex` 下可能有多个 `state_N.sqlite`，需要自动找最新的

### 4. 费用计算
- Hermes：`estimated_cost_usd` 字段已有
- Codex：tokens_used 需要结合 model 查单价换算（定价表内置）
- 定价表做成一个 dict，随时可更新

### 5. 时间过滤
- 默认显示最近 7 天
- `--days` / `--since` / `--until` 参数
- 在 SQL 层过滤，不要在 Python 层过滤

---

## 八、测试策略

Phase 1 暂时不做完整的单元测试（MVP 阶段成本优先），但验证方式：

1. 真实数据验证：每次写完一个 Collector，跑 `python -c "from src.collectors.hermes import HermesCollector; c=HermesCollector(); print(len(c.collect()))"` 看能否正常读
2. 空数据测试：如果 DB 不存在或表为空，不能崩溃
3. 编码兼容测试：Windows 路径的中文用户名 → 确保 /mnt/c/ 路径能正确拼接

---

## 九、阶段拆解

建议分 5 轮迭代：

**第 1 轮：骨架 + 插件体系**
- pyproject.toml + models + base collector + CollectorRegistry（内置+用户自定义双路径自动发现）+ main.py
- 重点把插件体系搭好，确保：
  - `src/collectors/` 下的 `.py` 文件自动注册为内置 collector
  - `~/.ai-spend/collectors/` 下的 `.py` 文件自动注册为用户自定义 collector
  - 用户自定义和内置享有完全相同的接口和待遇
- 验证：`pip install -e . && ai-spend` 能跑，`ai-spend --list-agents` 显示 0 个可用

**第 2 轮：Hermes Collector（第一个内置插件）**
- hermes.py + config.py + display.py（基础表格）
- 用第一个真实 collector 打通全链路：读取 → 聚合 → 显示
- 这一轮要验证插件架构是对的——写 hermes.py 时一行 main.py 都没改
- 验证：`ai-spend` 能看到 Hermes 真实数据

**第 3 轮：Codex Collector（第二个内置插件）**
- codex.py
- 只加一个文件就多了新 agent 的数据，验证架构的扩展性
- 验证：`ai-spend` 能看到 Hermes + Codex 合计

**第 4 轮：用户自定义 collector**
- `ai-spend init` 命令：在 `~/.ai-spend/collectors/` 下生成模板文件
- 完善文档，给用户看如何写自定义 collector
- 验证：写一个假的自定义 collector，`ai-spend` 能认出来并显示

**第 5 轮：打磨**
- 时间过滤、JSON 输出、README、代码整理
- 验证：所有命令行参数正常工作
