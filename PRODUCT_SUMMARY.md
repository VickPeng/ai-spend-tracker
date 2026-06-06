# AI Spend Tracker — 产品汇总

> 生成日期：2026-06-06
> 整理自小谢（vick）与 Hermes Agent 的多次讨论

---

## 一、项目背景

### 你是谁
- 昵称小谢，2024年7月外包入职**长江存储（YMTC）**做前端开发（自动化测试平台）
- 面临转正压力（AI冲击导致转正机会变小）
- 副业规划：①开发面向海外的独立软件产品（学Python后端）②跨境电商独立站 ③短视频引流 ④国际平台接单
- 目标：1.5年内副业连续半年月入8000元 → 辞职
- 正在学 Python 后端，关注 AI 应用方向

### 你的现状工具
| 工具 | 位置 | 用途 |
|------|------|------|
| Claude Code v2.1.165 | Windows (npm全局) | 编码 agent |
| Codex CLI 0.135.0 | Windows (npm全局) | 编码 agent |
| Hermes Agent | Windows + WSL2 | 你正在跟我聊天 |
| OpenClaw | Windows (npm全局) | 编码 agent |

### 你使用的 LLM Provider
| Provider | 模型 |
|----------|------|
| DeepSeek（主力） | v4-pro / v4-flash |
| Qwen (DashScope) | qwen3.7-max |
| MiniMax-CN | M2.7 / M3 |

---

## 二、产品定义：AI Spend Tracker

### 核心痛点
同时使用多个 AI 编码 agent + 多个 LLM provider，token 消耗和费用散落在各个工具中，看不到**全貌**。

### 一句话
> 一个跨平台、跨 provider 的 AI Token 用量 & 费用聚合看板。

### 目标用户画像
- **个人开发者**：同时使用多个 AI agent（Claude Code、Hermes、Codex、OpenClaw）
- **小团队**：多人共享多个 AI 工具，想控制成本
- **企业**：需要看到团队整体的 AI 费用开销

---

## 三、产品路线图（三段式）

### Phase 1 — 免费 CLI 工具（MVP）
- 本地运行，读取各个工具的 session 日志
- 聚合展示 token 用量和费用
- 技术栈：Python CLI

### Phase 2 — 免费 SaaS 看板
- 云端面板，Web UI
- 支持多设备数据上报
- 提供历史趋势图表

### Phase 3 — 付费 Pro 版
- 代理模式（流量统一经过网关，精确统计）
- 团队协作功能
- 费用告警 / 预算设置
- 多 workspace 管理

---

## 四、Phase 1 技术调研结论

### 数据源可用性

| 工具 | 数据位置 | token数据 | 读取方式 |
|------|---------|-----------|---------|
| **Hermes Agent (WSL2)** | `~/.hermes/state.db` | ✅ 完整 — input/output/cache/reasoning tokens + 费用估算 | Python sqlite3 直接读 |
| **Codex (Windows)** | `~/.codex/state_5.sqlite` | ✅ `tokens_used` + `model_provider` + `model` | 通过 /mnt/c/ 路径读取 |
| **Claude Code (Windows)** | `~/.claude/history.jsonl` | ❌ **只存对话文本，无 token 记录** | 需要额外方案 |
| **OpenClaw** | 待确认 | 待确认 | 待调研 |

### Hermes Agent state.db sessions 表关键字段
```
id, source, model, started_at, ended_at
message_count, tool_call_count
input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, reasoning_tokens
estimated_cost_usd, actual_cost_usd, billing_provider
```

### Codex state_5.sqlite threads 表关键字段
```
id, title, created_at, updated_at
model_provider, tokens_used, model
```

### Claude Code 的数据缺失问题
Claude Code 对话结束时终端会打印 Token usage 信息，但不写入结构化文件。可能的解决方案：
1. 拦截 Claude Code 输出（hooks）
2. 解析 history.jsonl 配合 session 时长估算
3. 通过代理模式统计（Phase 3）

### 开发环境
- **开发机**：WSL2 (Ubuntu 24.04) + Windows 双环境
- **代码存放**：`D:\acode\ai-spend-tracker\`（/mnt/d/acode/ai-spend-tracker/）
- **C盘空间紧张**，所以代码放 D 盘
- Python 3.10+，依赖 tabulate / rich

### 工具协作方案
- Hermes Agent 作为**总指挥**，负责架构设计、文件读写、测试
- Claude Code / Codex 通过 `delegate_task` + `terminal()` 调用（`cmd.exe /c "claude -p '任务'"`）
- 或者直接在 WSL2 里 npm 安装一份，更方便

---

## 五、关键风险

1. **Claude Code 没有结构化 token 数据** — Phase 1 可能只能覆盖 Hermes + Codex
2. **国内市场** — 主要面向海外开发者（英文产品），需要海外推广渠道
3. **竞品** — 各 AI agent 厂商自己也有用量统计（Claude Code 的 /cost 命令），但跨平台聚合是差异化
4. **Phase 1 免费 → Phase 3 付费的转化路径** — 需要设计好免费版的价值锚点
5. **你的时间** — 白天有全职工作（外包前端），副业时间有限

---

## 六、关于你个人的补充信息

- 白天上班：长江存储外包前端（自动化测试平台）
- 业余学习：Python 后端（FastAPI），准备做 SaaS
- 健康目标：减重10斤，控烟控酒，12点前睡
- 经济目标：2027下半年实现26万存款、买机车、旅游一次
- 工具偏好：能用中文沟通，喜欢简洁结构化回复
- QQ 机器人有定时任务：每日早安播报（7:50）、每周资讯播报（周五20:30）
