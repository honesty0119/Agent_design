# Minimal Agent Runtime

一个不依赖 LangGraph、OpenHands、OpenClaw 等 Agent 框架的最小可用 Agent Runtime。项目实现了完整的 **LLM → 决策 → 工具调用 → 结果回填 → 再决策** 循环，并提供会话隔离、上下文压缩、SQLite 持久化、执行日志、自动化测试和可直接操作的网页。

> 默认使用 Mock LLM，因此不配置密钥也能运行。提交或演示时切换到真实的 OpenAI-compatible API。

## 已实现能力

- 自行实现 Agent Runtime 主循环，最多执行轮数可配置
- OpenAI-compatible Chat Completions / Tool Calling 适配器
- 真实模型增量流式输出，支持流式 Tool Calling 参数组装
- Calculator、本地项目检索、Todo、Context Stats 四个 Schema 工具
- 工具注册、参数边界校验、超时和结构化错误
- 多 Session 隔离，同一 Session 内请求串行执行
- SQLite 保存会话、消息、Todo 和 Trace
- 长 Context 的“历史摘要 + 最近消息”压缩策略
- 重复工具调用检测，避免无限循环
- 模型网络错误重试和安全错误响应
- ChatGPT 风格 Web 界面、会话行内重命名与删除
- REST API、Swagger 文档
- 覆盖工具、安全限制、Session 隔离、Context 压缩和循环保护的测试

## 系统结构

```text
浏览器 / API Client
        │
        ▼
     FastAPI
        │
        ▼
  Session Lock ─────────────── SQLite
        │                 sessions/messages/todos/traces
        ▼
  Context Builder
        │
        ▼
  Agent Runtime Loop
   ├─ LLM Client (Mock / OpenAI-compatible)
   ├─ Tool Registry
   ├─ Tool Executor + Timeout
   └─ Trace Logger
```

一次请求的执行流程：

1. 校验 Session，并将用户消息写入数据库。
2. Context Builder 组合 System Prompt、历史摘要和最近消息。
3. LLM 返回最终回答，或者返回结构化工具调用。
4. Runtime 校验重复调用并将工具请求写入消息历史。
5. Tool Registry 在超时约束内执行工具，返回统一的 ToolResult。
6. 工具结果作为 tool 消息回填 Context，继续请求 LLM。
7. 模型文本增量通过 NDJSON 推送到网页，直接追加到当前消息区。
8. 得到最终回答，或达到最大轮次后安全终止。

## 目录说明

```text
app/
├── config.py                 # 环境配置和 System Prompt
├── context.py                # Context 构建与压缩
├── database.py               # SQLite Session/Message/Todo/Trace
├── factory.py                # 依赖组装
├── main.py                   # FastAPI 接口
├── models.py                 # 领域模型与 API Schema
├── runtime.py                # Agent 主循环
├── llm/
│   ├── base.py               # LLM 协议和异常
│   ├── mock.py               # 无密钥可运行的 Mock LLM
│   └── openai_compatible.py  # 真实模型 API 适配器
├── tools/
│   ├── base.py               # Tool 接口与执行上下文
│   ├── registry.py           # 注册、路由、超时与异常边界
│   └── builtin.py            # Calculator/Search/Todo/ContextStats
└── static/index.html         # 多会话网页

tests/                        # 自动化测试
.env.example                  # 配置模板
pyproject.toml                # 依赖和测试配置
```

## 快速开始

### 1. 创建环境并安装

要求 Python 3.11 或更高版本。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

macOS/Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

### 2. 启动

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开：

- 网页：http://127.0.0.1:8000
- Swagger：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

Mock 模式可以尝试：

- `12*(3+4) 等于多少？`
- `帮我在项目文件中查找 ContextBuilder`
- `帮我记下明天上午九点写周报`
- `列出我的待办`
- `把 1 号待办标记为完成`
- `当前 Context 是否触发了压缩？`

## 使用真实 LLM API

复制 `.env.example` 为 `.env` 后修改：

```dotenv
AGENT_LLM_MODE=openai-compatible
AGENT_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AGENT_LLM_API_KEY_ENV=OPENAI_API_KEY
AGENT_LLM_MODEL=qwen-plus
```

当前项目已经按上面的 DashScope（华北 2/北京）配置完成。密钥从
`OPENAI_API_KEY` 系统环境变量读取，不会写入 `.env` 或源代码。修改
系统环境变量后，需要重新打开终端并重启服务，旧进程不会自动获得新变量。

也可填写其他兼容 OpenAI `/chat/completions` 和 Tool Calling 格式的服务地址与模型名。不同提供商对消息字段的兼容程度可能不同；适配差异应集中修改 `app/llm/openai_compatible.py`，不要侵入 Runtime。

## API 示例

创建会话：

```bash
curl -X POST http://127.0.0.1:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"窗口一"}'
```

发送消息（替换 SESSION_ID）：

```bash
curl -X POST http://127.0.0.1:8000/api/sessions/SESSION_ID/messages \
  -H "Content-Type: application/json" \
  -d '{"content":"计算 23*17"}'
```

流式发送消息：

```text
POST /api/sessions/{session_id}/messages/stream
Content-Type: application/json

{"content":"帮我计算 23*17"}
```

流式接口返回逐行 NDJSON 事件：

```text
start → tool_call → tool_result
→ assistant_delta ... → done
```

查看消息与 Trace：

```text
GET /api/sessions/{session_id}/messages
GET /api/sessions/{session_id}/traces
```

重命名与删除会话：

```text
PATCH  /api/sessions/{session_id}  body: {"title": "新的名称"}
DELETE /api/sessions/{session_id}
```

重命名只更新会话名称和最后更新时间，不会改变 `created_at`。删除会话时，
SQLite 外键会级联删除该会话的消息、待办和 Trace。

## Web 界面

- 深色中性布局，侧栏与消息区参考 ChatGPT 的信息层级。
- 左侧每个会话独立显示名称和创建时间。
- 点击铅笔按钮可行内重命名，按 Enter 或点击外部保存，Esc 取消。
- 点击删除按钮后必须通过确认弹窗，避免误删。
- 工具执行结果默认折叠为“工具调用”卡片，可按需展开查看 JSON。
- 回答使用真实 LLM streaming API 增量追加，不等待完整答案一次性展示。
- 每轮发送后只更新当前消息和左侧会话顺序，不重新加载整个聊天页面。
- 输入框提示语为“有问题，尽管问”，支持 Enter 发送、Shift+Enter 换行。
- 移动端可通过顶部菜单按钮打开会话侧栏。

## Context 管理

Context Builder 并不把数据库中的全部历史无限塞给模型：

- 未超过 `AGENT_MAX_CONTEXT_CHARS` 时保留完整历史。
- 超过限制后，将较早的用户事实、助手结论和关键工具结果压缩为结构化摘要。
- 最近 `AGENT_RECENT_MESSAGES` 条消息尽量原样保留。
- 裁剪后删除开头孤立的 tool 消息，避免模型 API 拒绝非法消息序列。
- 每次构建都会写入 `context_built` Trace，记录原始字符数、最终字符数、压缩状态、摘要来源消息数和保留的最近消息数。

当前摘要器是确定性的抽取式实现，便于测试且不增加模型调用成本。生产环境可替换为独立的小模型摘要器，但应保留结构化摘要契约，并重点保留：用户约束、已确认事实、已完成任务、待处理任务和关键工具结果。

当用户询问 Context 长度或压缩状态时，LLM 应调用只读的
`context_stats` 工具；System Prompt 明确禁止使用 Calculator 或 Search
猜测这些内部数据。

## Session 与并发策略

- 每个聊天窗口使用独立 UUID，消息和 Todo 都通过 `session_id` 隔离。
- 同一进程内，每个 Session 有独立的 `asyncio.Lock`，同一会话请求按顺序执行。
- 不同 Session 可以并行执行，互不阻塞。
- Session 状态包括 `idle`、`running`、`failed`。

本方案适用于单进程笔试和本地演示。若扩展到多实例部署，应把 Session 锁替换为 Redis 分布式锁或基于队列的 Session Actor/Mailbox，并为消息加入 turn/version 字段。

## 工具机制

每个工具实现三个核心字段和一个执行方法：

```python
class Tool:
    name: str
    description: str
    input_schema: dict

    async def execute(self, arguments, context) -> ToolResult:
        ...
```

LLM 只看到名称、描述和 JSON Schema。Tool Registry 负责：

- 按名称查找工具
- 统一超时
- 把参数错误、业务错误和未知异常转成 ToolResult
- 防止工具异常直接击穿 Runtime

新增工具时，在 `app/tools/builtin.py` 中实现 Tool，并在 `app/factory.py` 注册即可。

当前内置工具：

- `calculator`：AST 白名单算术计算。
- `search`：实际扫描本地项目的 Markdown、Python、TOML、HTML 和 JSON 文件；不回退到无关固定结果，也不声称是互联网搜索。
- `todo`：按 Session 新增、列出和完成待办；截止时间必须是带时区偏移的 ISO-8601 时间。
- `context_stats`：只读返回本轮 Context 的真实构建统计。

### 安全说明

Calculator 使用 Python AST 白名单，只允许数字、括号和基础运算符，不使用 `eval`。同时限制表达式长度、AST 深度、数值大小和指数，避免代码执行与明显的资源滥用。

Todo 返回明确的 `pending` / `completed` 状态。System Prompt 约定
待处理使用 `⬜`，已完成使用 `✅`；当用户表达相对时间时，Runtime 会向
模型提供配置时区下的当前时间，模型再生成带时区的 `due_time`。

## 可观测性

每次用户请求生成 `trace_id`，数据库记录：

- 用户消息长度
- Context 是否压缩、压缩前后字符数、摘要来源和最近消息保留数
- 每一步 LLM 决策及耗时
- Token usage（提供商返回时）
- 工具名称、耗时、成功状态、是否可重试
- 模型错误、重复调用、最大轮次终止

接口 `GET /api/sessions/{session_id}/traces` 可用于问题复现和录屏展示。Trace 不保存 API Key，也不记录模型的隐藏思维过程。

## 测试

```bash
python -m pytest
```

测试内容包括：

- 合法计算与代码执行阻断
- 本地项目检索只返回真实匹配
- Todo 截止时间的时区校验
- Context Stats 工具返回真实测量数据
- LLM → Tool → LLM 完整循环
- 流式 Tool Calling、工具结果和最终回答事件顺序
- 两个 Session 的数据隔离
- 重复工具调用保护
- 最大执行轮数保护
- 长对话触发 Context 压缩

自动化测试使用 Mock/Scripted LLM，不消耗真实 API。正式验收时再使用真实模型进行端到端测试。

## 关键配置

| 配置 | 默认值 | 说明 |
|---|---:|---|
| `AGENT_LLM_MODE` | `mock` | `mock` 或 `openai-compatible` |
| `AGENT_LLM_BASE_URL` | OpenAI URL | 模型服务地址 |
| `AGENT_LLM_API_KEY_ENV` | `AGENT_LLM_API_KEY` | 保存密钥的环境变量名称 |
| `AGENT_LLM_MODEL` | `gpt-4.1-mini` | 模型名 |
| `AGENT_DATABASE_PATH` | `data/agent_runtime.db` | SQLite 文件 |
| `AGENT_MAX_STEPS` | `8` | 单次 Agent 最大循环数 |
| `AGENT_TOOL_TIMEOUT_SECONDS` | `15` | 单次工具超时 |
| `AGENT_MAX_CONTEXT_CHARS` | `24000` | MVP Context 大小近似阈值 |
| `AGENT_RECENT_MESSAGES` | `12` | 压缩时保留的最近消息数 |
| `AGENT_TIMEZONE` | `Asia/Shanghai` | 解析相对 Todo 截止时间时使用的时区 |

字符数只是无 tokenizer 依赖下的保守近似。生产环境应接入具体模型 tokenizer，并分别预留输出 Token 和工具 Schema 的预算。

## 当前边界与后续演进

这是刻意保持清晰的小型 Runtime，暂未实现：

- 互联网搜索服务（当前 Search 是真实的本地项目检索）
- 多工具并行调用
- 跨 Session 的长期用户 Memory
- 多进程分布式锁
- 异步长任务的后台 Worker 和完成通知
- 模型驱动的持久化历史摘要

推荐演进顺序：

1. 给消息增加 turn/version，支持异步工具完成事件。
2. 引入 Session Mailbox，统一处理用户消息和工具事件。
3. 增加后台任务表、Worker、取消与幂等机制。
4. 接入联网搜索，并增加权限、来源引用和审计层。
5. 将 Trace 导出到 OpenTelemetry。
6. 增加长期 Memory 的写入判断、检索、衰减和用户可控删除。

## 录屏建议

1. 启动网页，新建“窗口一”和“窗口二”。
2. 窗口一添加待办，窗口二列出待办，展示 Session 隔离。
3. 执行计算和搜索，展示消息历史中的工具调用结果。
4. 打开 Swagger 或 Trace 接口，展示执行步数与耗时。
5. 切换到真实 API，完成一次真实模型 Tool Calling。

这样可以同时证明主循环、工具机制、会话隔离和可观测性，而不只是展示聊天 UI。
