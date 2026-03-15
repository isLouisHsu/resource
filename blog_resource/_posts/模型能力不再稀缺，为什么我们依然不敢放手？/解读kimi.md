# Kimi Code CLI 项目深度解读

## 概述

Kimi Code CLI 是一个基于 Python 构建的 AI Agent CLI 工具，采用 React + Vite 构建 Web UI。项目使用 `uv` 作为包管理器，采用 monorepo 结构管理多个工作区包。

---

## 一、项目整体结构

```
kimi-cli/
├── src/kimi_cli/              # 主 CLI 包（135+ Python 文件）
│   ├── agents/                # 内置 Agent 定义（YAML + 系统提示词）
│   ├── cli/                   # Typer 命令行入口
│   ├── soul/                  # 核心 Agent 逻辑
│   │   ├── kimisoul.py        # 主循环
│   │   ├── agent.py           # Runtime 和 Agent 定义
│   │   ├── context.py         # 消息上下文管理
│   │   └── toolset.py         # 工具集管理
│   ├── tools/                 # 工具实现
│   ├── ui/                    # UI 实现（shell, print, acp, web）
│   ├── wire/                  # 通信协议
│   ├── skill/                 # Skill 系统
│   ├── acp/                   # Agent Client Protocol
│   └── web/                   # Web UI 后端
├── packages/                  # 工作区包
│   ├── kosong/                # LLM 抽象层（支持 Kimi, OpenAI, Anthropic, Gemini）
│   ├── kaos/                  # 异步文件系统和 SSH 抽象
│   └── kimi-code/             # 额外能力
├── sdks/kimi-sdk/             # Python SDK
├── web/                       # React + Vite 前端
├── tests/                     # 单元测试
└── tests_e2e/                 # 端到端测试
```

---

## 二、核心架构详解

### 2.1 架构总览

Kimi CLI 采用分层架构设计，核心分为以下几个层次：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              UI 层                                       │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐│
│  │Shell (交互)  │ │Print (批处理)│ │Web (浏览器)  │ │ACP (协议服务器)      ││
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────────┬──────────┘│
└─────────┼───────────────┼───────────────┼───────────────────┼───────────┘
          │               │               │                   │
          └───────────────┴───────┬───────┴───────────────────┘
                                  │
                          ┌───────▼────────┐
                          │   Wire 协议层   │  ← 单生产者多消费者消息通道
                          └───────┬────────┘
                                  │
                          ┌───────▼────────┐
                          │   KimiSoul     │  ← Agent 主循环核心
                          │   (Agent Loop) │
                          └───────┬────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
   ┌──────▼──────┐      ┌─────────▼──────────┐  ┌────────▼────────┐
   │   Agent     │      │     Runtime        │  │     Context     │
   │  (配置+工具) │      │    (执行上下文)     │  │   (消息历史)     │
   └─────────────┘      └────────────────────┘  └─────────────────┘
```

### 2.2 各核心组件详解

#### 2.2.1 KimiCLI（入口层）

**位置**: `src/kimi_cli/cli/`

KimiCLI 是整个应用的入口点，主要职责：
- 解析命令行参数
- 加载配置（TOML/JSON）
- 创建/恢复 Session
- 初始化 Runtime
- 加载 Agent
- 创建 KimiSoul
- 启动对应 UI 模式

**初始化流程**:
```
1. 解析命令行参数
2. 加载配置（TOML/JSON）
3. 创建/恢复 Session
4. 初始化 Runtime
5. 加载 Agent
6. 创建 KimiSoul
7. 启动对应 UI 模式
```

#### 2.2.2 Config（配置层）

**位置**: `src/kimi_cli/config.py`

**配置文件位置**: `~/.config/kimi/config.toml`

Config 是整个系统的配置中心，包含：

```python
class Config(BaseModel):
    default_model: str                    # 默认模型
    default_thinking: bool                # 默认启用思考模式
    default_yolo: bool                    # 默认启用 YOLO 模式（自动批准）
    models: dict[str, LLMModel]          # 模型定义
    providers: dict[str, LLMProvider]    # 提供商配置
    loop_control: LoopControl            # 循环控制参数
    services: Services                   # 服务配置
    mcp: MCPConfig                       # MCP 配置
```

**关键配置项**:
- **models**: 定义各模型的能力（context window、支持的功能等）
- **providers**: LLM 提供商的 base_url 和 api_key
- **loop_control**: 最大迭代次数、重试设置、压缩触发阈值等
- **mcp**: Model Context Protocol 服务器配置

**环境变量覆盖**:
- `KIMI_BASE_URL` - API 基础 URL
- `KIMI_API_KEY` - API 密钥
- `KIMI_MODEL_NAME` - 模型名称
- `KIMI_MODEL_MAX_CONTEXT_SIZE` - 最大上下文大小

#### 2.2.3 Runtime（执行上下文）

**位置**: `src/kimi_cli/soul/agent.py`

Runtime 是执行上下文容器，贯穿整个应用生命周期：

```python
@dataclass
class Runtime:
    config: Config              # 全局配置
    oauth: OAuthManager         # OAuth 认证管理
    llm: LLM | None            # LLM 实例（延迟加载）
    session: Session            # 当前会话
    builtin_args: BuiltinSystemPromptArgs  # 系统提示词参数
    denwa_renji: DenwaRenji     # D-Mail（时间旅行）管理器
    approval: Approval          # 审批管理
    labor_market: LaborMarket   # 子 Agent 劳动力市场
    environment: Environment    # 环境检测（OS、Shell 等）
    skills: dict[str, Skill]    # 已加载的 Skills
    additional_dirs: list[KaosPath]  # 额外工作目录
```

**核心职责**:
1. **依赖注入**: 为 Tools 提供所需的依赖（如 Approval、Session 等）
2. **状态共享**: 在 Soul、Agent、Tools 之间共享状态
3. **生命周期管理**: 管理会话、认证、审批等生命周期
4. **子 Agent 管理**: LaborMarket 管理子 Agent 的注册和调用

#### 2.2.4 Agent（配置实体）

**位置**: `src/kimi_cli/soul/agent.py`

Agent 是一个纯配置实体，包含：

```python
@dataclass(frozen=True)
class Agent:
    name: str                   # Agent 名称
    system_prompt: str          # 系统提示词（Jinja2 渲染后）
    toolset: Toolset            # 工具集
    runtime: Runtime            # 执行上下文
```

**特性**:
- **不可变**: Agent 是 immutable 的，确保配置安全
- **YAML 定义**: 通过 YAML 文件定义，支持继承
- **动态加载**: 支持运行时动态创建子 Agent

**Agent YAML 定义**:
```yaml
version: 1
agent:
  name: "default"
  system_prompt_path: ./system.md
  system_prompt_args:
    ROLE_ADDITIONAL: ""
  tools:
    - "kimi_cli.tools.file:ReadFile"
    - "kimi_cli.tools.file:WriteFile"
    - "kimi_cli.tools.shell:Shell"
  subagents:
    coder:
      path: ./coder.yaml
      description: "Good at coding tasks"
```

#### 2.2.5 KimiSoul（主循环核心）

**位置**: `src/kimi_cli/soul/kimisoul.py`

KimiSoul 是整个系统的核心，负责：
- 管理 Agent 主循环
- 处理用户输入和斜杠命令
- 协调 LLM 调用和工具执行
- 上下文压缩和管理
- D-Mail（时间旅行）处理

**核心属性**:
```python
class KimiSoul:
    _agent: Agent                    # 当前 Agent
    _context: Context                # 消息上下文
    _runtime: Runtime                # 执行上下文
    _loop_control: LoopControl       # 循环控制参数
    _denwa_renji: DenwaRenji         # D-Mail 管理器
    _pending_user_message: UserMessage | None  # 待处理的用户消息
```

#### 2.2.6 Context（消息上下文）

**位置**: `src/kimi_cli/soul/context.py`

Context 管理对话历史：

```python
class Context:
    _history: list[Message]          # 消息历史
    _token_count: int                # 当前 Token 计数
    _next_checkpoint_id: int         # 下一个检查点 ID
    _file_backend: Path              # 持久化文件路径
```

**核心功能**:
- 消息添加和持久化
- 检查点（checkpoint）创建和回滚
- Token 计数跟踪
- 从文件恢复上下文

#### 2.2.7 Wire（通信协议）

**位置**: `src/kimi_cli/wire/`

Wire 是 Soul 和 UI 之间的通信协议，采用**单生产者多消费者**模式：

```python
class Wire:
    _raw_queue: BroadcastQueue[WireMessage]      # 原始消息队列
    _merged_queue: BroadcastQueue[WireMessage]   # 合并后的消息队列
```

**消息类型**:
- `TurnBegin` / `TurnEnd`: 回合开始/结束
- `ContentPart`: 内容片段（文本、图片等）
- `ToolCall`: 工具调用
- `ToolResult`: 工具执行结果
- `ApprovalRequest`: 审批请求
- `Checkpoint`: 检查点标记

---

## 三、Agent Loop 详解

### 3.1 整体流程

```
┌────────────────────────────────────────────────────────────────┐
│                        Agent Loop                               │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐                                               │
│  │  用户输入   │                                               │
│  └──────┬──────┘                                               │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────────┐     是      ┌──────────────────┐         │
│  │ 是否斜杠命令？   │───────────▶│ 执行斜杠命令      │         │
│  └────────┬────────┘            └────────┬─────────┘         │
│           │ 否                            │                   │
│           ▼                               │                   │
│  ┌─────────────────┐                      │                   │
│  │   添加到上下文   │◀─────────────────────┘                   │
│  └────────┬────────┘                                          │
│           │                                                    │
│           ▼                                                    │
│  ┌──────────────────────────────────────────┐                 │
│  │            Agent Loop 开始                │                 │
│  │  ┌────────────────────────────────────┐  │                 │
│  │  │ Step 1: 检查上下文是否需要压缩      │  │                 │
│  │  │        (token_count > threshold)    │  │                 │
│  │  └──────────────┬─────────────────────┘  │                 │
│  │                 │ 是                      │                 │
│  │                 ▼                         │                 │
│  │  ┌────────────────────────────────────┐  │                 │
│  │  │ 执行上下文压缩(SimpleCompaction)    │  │                 │
│  │  └──────────────┬─────────────────────┘  │                 │
│  │                 │                        │                 │
│  │                 ▼                        │                 │
│  │  ┌────────────────────────────────────┐  │                 │
│  │  │ Step 2: 调用 LLM                    │  │                 │
│  │  │  - 发送 system_prompt + history    │  │                 │
│  │  │  - 获取 assistant 回复              │  │                 │
│  │  └──────────────┬─────────────────────┘  │                 │
│  │                 │                        │                 │
│  │                 ▼                        │                 │
│  │  ┌────────────────────────────────────┐  │                 │
│  │  │ Step 3: 处理 LLM 回复               │  │                 │
│  │  │  - 提取文本内容                     │  │                 │
│  │  │  - 提取工具调用                     │  │                 │
│  │  └──────────────┬─────────────────────┘  │                 │
│  │                 │                        │                 │
│  │                 ▼                        │                 │
│  │  ┌────────────────────────────────────┐  │                 │
│  │  │ Step 4: 执行工具调用                │  │                 │
│  │  │  - 并行执行多个工具                 │  │                 │
│  │  │  - 等待执行结果                     │  │                 │
│  │  └──────────────┬─────────────────────┘  │                 │
│  │                 │                        │                 │
│  │                 ▼                        │                 │
│  │  ┌────────────────────────────────────┐  │                 │
│  │  │ Step 5: 检查结果                    │  │                 │
│  │  │  - 是否有 D-Mail？                  │  │                 │
│  │  │  - 是否达到最大迭代次数？            │  │                 │
│  │  │  - 是否有工具调用？                  │  │                 │
│  │  └──────────────┬─────────────────────┘  │                 │
│  │                 │                        │                 │
│  │    ┌────────────┼────────────┐          │                 │
│  │    │            │            │          │                 │
│  │    ▼            ▼            ▼          │                 │
│  │  继续循环    结束循环    抛出异常        │                 │
│  │  (有工具)   (无工具)    (D-Mail)        │                 │
│  └──────────────────────────────────────────┘                 │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 3.2 代码详解

#### 3.2.1 run 方法（入口）

```python
async def run(self, user_input: str | list[ContentPart]):
    """处理用户输入的主入口"""
    # 1. 发送 TurnBegin 事件到 UI
    wire_send(TurnBegin(user_input=user_input))

    try:
        # 2. 处理斜杠命令
        if command_call := parse_slash_command_call(text_input):
            await self._execute_slash_command(command_call)
        # 3. 执行 Agent Loop
        elif self._loop_control.max_ralph_iterations != 0:
            # Ralph 模式：自动循环直到完成
            await self._ralph_loop(user_message)
        else:
            # 普通模式：单轮交互
            await self._turn(user_message)
    finally:
        # 4. 发送 TurnEnd 事件
        wire_send(TurnEnd())
```

#### 3.2.2 _agent_loop 方法（核心循环）

```python
async def _agent_loop(self, user_message: UserMessage) -> TurnOutcome:
    """Agent 核心循环"""
    step_no = 0
    outcome_messages: list[Message] = []

    while True:
        step_no += 1

        # 1. 检查是否需要上下文压缩
        if should_auto_compact(
            token_count=self._context.token_count(),
            max_context_size=self._runtime.config.get_model().max_context_size,
            trigger_ratio=self._loop_control.auto_compact_trigger_ratio,
        ):
            await self.compact_context()

        # 2. 执行单步
        step_outcome = await self._step()

        # 3. 处理 D-Mail（时间旅行）
        if dmail := self._denwa_renji.fetch_pending_dmail():
            raise BackToTheFuture(dmail.checkpoint_id, dmail.messages)

        # 4. 检查停止条件
        if step_outcome.stop_reason == "no_tool_calls":
            # Assistant 没有调用工具，回合结束
            return TurnOutcome(
                finish_reason="completed",
                messages=outcome_messages,
            )

        if step_no >= self._loop_control.max_iterations:
            # 达到最大迭代次数
            return TurnOutcome(
                finish_reason="max_iterations_reached",
                messages=outcome_messages,
            )
```

#### 3.2.3 _step 方法（单步执行）

```python
async def _step(self) -> StepOutcome:
    """执行单步：调用 LLM 并处理结果"""
    # 1. 获取 ChatProvider
    chat_provider = await self._runtime.llm.get_chat_provider()

    # 2. 调用 LLM
    result = await kosong.step(
        chat_provider=chat_provider,
        system_prompt=self._agent.system_prompt,
        toolset=self._agent.toolset,
        messages=self._context.history,
        on_message_part=lambda p: wire_send(ContentPartMessage(p)),
        on_tool_result=lambda r: wire_send(ToolResultMessage(r)),
    )

    # 3. 等待工具执行结果
    tool_results = await result.tool_results()

    # 4. 更新上下文
    await self._grow_context(result, tool_results)

    # 5. 确定停止原因
    stop_reason = "no_tool_calls" if not result.tool_calls else "tool_calls"

    return StepOutcome(
        assistant_message=result.assistant_message,
        tool_results=tool_results,
        stop_reason=stop_reason,
    )
```

---

## 四、KimiSoul 完整执行流程（从 run() 入口开始）

### 4.1 场景设定

假设用户在工作目录 `/Users/louishsu/project` 中，输入了一个复杂任务：

```
帮我分析这个项目的代码结构，找出所有 API 端点，然后给每个端点添加单元测试
```

### 4.2 第一阶段：入口 run()

```python
async def run(self, user_input: str | list[ContentPart]):
    # 1. 刷新 OAuth token（避免过期）
    await self._runtime.oauth.ensure_fresh(self._runtime)

    # 2. 发送 TurnBegin 事件到 UI（开始新回合）
    wire_send(TurnBegin(user_input=user_input))

    # 3. 创建用户消息
    user_message = Message(role="user", content=user_input)
    text_input = user_message.extract_text(" ").strip()  # "帮我分析..."
```

**此时的消息流：**
```
[Wire] TurnBegin(user_input="帮我分析...")
[UI]  显示用户输入
```

**判断输入类型：**

```python
    # 4. 检查是否是斜杠命令（如 /clear, /yolo 等）
    if command_call := parse_slash_command_call(text_input):
        # 用户输入了 /clear, /compact 等命令
        command = self._find_slash_command(command_call.name)
        ret = command.func(self, command_call.args)
        if isinstance(ret, Awaitable):
            await ret
```

**场景分支 A：如果是斜杠命令**

假设用户输入 `/compact`（手动压缩上下文）：

```
用户输入: /compact
    ↓
parse_slash_command_call 解析出 name="compact", args=""
    ↓
_find_slash_command("compact") → 返回 compact 命令
    ↓
执行 compact 命令 → 调用 compact_context()
    ↓
发送 CompactionBegin → UI 显示"正在压缩上下文..."
    ↓
调用 LLM 总结历史消息
    ↓
替换上下文 → 发送 CompactionEnd
```

**场景分支 B：普通用户输入（继续主线）**

```python
    elif self._loop_control.max_ralph_iterations != 0:
        # Ralph 模式：自动循环执行直到完成
        runner = FlowRunner.ralph_loop(
            user_message,
            self._loop_control.max_ralph_iterations,
        )
        await runner.run(self, "")
    else:
        # 普通模式：单轮交互
        await self._turn(user_message)

    # 5. 回合结束
    wire_send(TurnEnd())
```

**继续主线，进入 `_turn()`：**

### 4.3 第二阶段：_turn() 初始化

```python
async def _turn(self, user_message: Message) -> TurnOutcome:
    # 检查 LLM 是否设置
    if self._runtime.llm is None:
        raise LLMNotSet()

    # 检查消息是否被当前 LLM 支持（如图片、视频等）
    if missing_caps := check_message(user_message, self._runtime.llm.capabilities):
        raise LLMNotSupported(...)

    # ★ 关键：创建检查点（checkpoint）
    await self._checkpoint()  # 创建 checkpoint 0

    # 将用户消息添加到上下文
    await self._context.append_message(user_message)

    # 进入核心 Agent Loop
    return await self._agent_loop()
```

**上下文状态变化：**
```
初始: []
    ↓
checkpoint(): checkpoint_id=0 创建
    ↓
append_message(UserMessage):
    [
        UserMessage("帮我分析..."),
        checkpoint_id=0
    ]
```

### 4.4 第三阶段：_agent_loop() 核心循环

这是整个系统的核心，分步骤讲解：

```python
async def _agent_loop(self) -> TurnOutcome:
    # 清理上一回合的 steer 队列
    while not self._steer_queue.empty():
        self._steer_queue.get_nowait()

    # 等待 MCP 工具加载完成
    if isinstance(self._agent.toolset, KimiToolset):
        loading = self._agent.toolset.has_pending_mcp_tools()
        if loading:
            wire_send(MCPLoadingBegin())  # UI 显示"MCP 加载中..."
        await self._agent.toolset.wait_for_mcp_tools()
        if loading:
            wire_send(MCPLoadingEnd())
```

#### 审批任务（并行运行）

```python
    # ★ 启动审批管道任务（在后台持续运行）
    async def _pipe_approval_to_wire():
        while True:
            request = await self._approval.fetch_request()  # 等待审批请求
            # 发送到 UI
            wire_request = ApprovalRequest(...)
            wire_send(wire_request)
            # 等待用户响应
            resp = await wire_request.wait()
            self._approval.resolve_request(request.id, resp)

    approval_task = asyncio.create_task(_pipe_approval_to_wire())
```

**这个任务在后台持续运行，当任何工具需要审批时，它会：**
1. 捕获审批请求
2. 发送到 UI 显示给用户
3. 等待用户点击"批准/拒绝"
4. 将结果返回给工具

#### Step 循环

```python
    step_no = 0
    while True:
        step_no += 1

        # 检查是否超过每回合最大步数
        if step_no > self._loop_control.max_steps_per_turn:
            raise MaxStepsReached(...)

        wire_send(StepBegin(n=step_no))  # UI 显示"Step 1/2/3..."

        try:
            # === 场景 1: 上下文压缩检查 ===
            if should_auto_compact(
                self._context.token_count,           # 当前 token 数
                self._runtime.llm.max_context_size,  # 最大上下文
                trigger_ratio=0.85,                   # 触发阈值 85%
            ):
                logger.info("Context too long, compacting...")
                await self.compact_context()  # ★ 执行压缩

            # 创建检查点
            await self._checkpoint()
            self._denwa_renji.set_n_checkpoints(self._context.n_checkpoints)

            # === 执行单步 ===
            step_outcome = await self._step()

        except BackToTheFuture as e:
            # === 场景 4: D-Mail 时间旅行 ===
            back_to_the_future = e
        except Exception:
            wire_send(StepInterrupted())
            raise
        finally:
            approval_task.cancel()  # 清理审批任务
```

### 4.5 第四阶段：_step() 单步执行

```python
async def _step(self) -> StepOutcome | None:
    chat_provider = self._runtime.llm.chat_provider

    # 1. 调用 LLM（带重试机制）
    result = await kosong.step(
        chat_provider,
        self._agent.system_prompt,      # 系统提示词
        self._agent.toolset,            # 可用工具
        self._context.history,          # 当前上下文
        on_message_part=wire_send,      # 流式输出回调
        on_tool_result=wire_send,       # 工具结果回调
    )

    # 2. 发送状态更新（token 使用情况）
    wire_send(StatusUpdate(
        token_usage=result.usage,
        context_usage=self._context_usage,  # 如 45%
    ))
```

**此时 UI 显示：**
```
[AI 正在思考...]
[输出文本...]
[调用工具: Glob]
```

#### 等待工具执行

```python
    # 3. 等待所有工具执行完成
    results = await result.tool_results()

    # 4. 更新上下文（添加 assistant 消息和工具结果）
    await asyncio.shield(self._grow_context(result, results))
```

### 4.6 场景详解

#### 场景 A：工具被调用（正常执行）

假设 LLM 输出：
```json
{
  "tool_calls": [
    {
      "id": "call_1",
      "name": "Glob",
      "arguments": {"pattern": "**/*.py"}
    },
    {
      "id": "call_2",
      "name": "Grep",
      "arguments": {"pattern": "@app\\.route|@router"}
    }
  ]
}
```

**执行流程：**
```
LLM 输出 tool_calls
    ↓
并行执行 Glob 和 Grep
    ↓
Glob 返回: ["src/main.py", "src/api.py", "src/utils.py"]
Grep 返回: ["src/api.py:10: @router.get(...)", "src/api.py:25: @router.post(...)"]
    ↓
调用 _grow_context() 添加结果到上下文
```

**_grow_context 执行：**
```python
async def _grow_context(self, result: StepResult, tool_results: list[ToolResult]):
    # 添加 assistant 消息（包含 tool_calls）
    await self._context.append_message(result.message)

    # 添加工具结果消息
    tool_messages = [tool_result_to_message(tr) for tr in tool_results]
    await self._context.append_message(tool_messages)
```

**上下文变为：**
```python
[
    SystemMessage("..."),
    UserMessage("帮我分析...", checkpoint_id=0),
    AssistantMessage(                        # AI 的回复
        content="我来帮你分析项目结构...",
        tool_calls=[ToolCall(id="call_1", ...), ToolCall(id="call_2", ...)]
    ),
    ToolResultMessage(                       # Glob 结果
        tool_call_id="call_1",
        content='["src/main.py", "src/api.py", ...]'
    ),
    ToolResultMessage(                       # Grep 结果
        tool_call_id="call_2",
        content='["src/api.py:10: @router.get", ...]'
    ),
]
```

#### 场景 B：需要审批的工具（如 WriteFile）

当工具需要审批时：

```python
    # 在工具内部（如 WriteFile）
    async def execute(self, file_path: str, content: str):
        # 1. 检查 YOLO 模式
        if self._approval.is_yolo():
            return await self._do_write(file_path, content)

        # 2. 发送审批请求
        approved = await self._approval.request(
            tool_name="WriteFile",
            action="write",
            description=f"Write to {file_path}",
        )

        if not approved:
            # 3. 用户拒绝
            return ToolResult(
                output="",
                error="User rejected the operation",
                return_value=ToolRejectedError()
            )

        return await self._do_write(file_path, content)
```

**审批流程图：**
```
WriteFile 工具执行
    ↓
approval.request()
    ↓
_pipe_approval_to_wire() 捕获请求
    ↓
wire_send(ApprovalRequest) → UI 显示弹窗
    ↓
用户点击"批准"或"拒绝"
    ↓
wire_request.wait() 返回结果
    ↓
如果拒绝: 返回 ToolRejectedError
```

**在 _step() 中处理拒绝：**
```python
    # 检查是否有工具被拒绝
    rejected = any(
        isinstance(result.return_value, ToolRejectedError)
        for result in results
    )
    if rejected:
        # 清理 D-Mail
        _ = self._denwa_renji.fetch_pending_dmail()
        return StepOutcome(
            stop_reason="tool_rejected",
            assistant_message=result.message
        )
```

#### 场景 C：子 Agent 调用（Task 工具）

当使用 `Task` 工具委派任务给子 Agent：

```python
# LLM 调用 Task 工具
{
  "name": "Task",
  "arguments": {
    "agent": "coder",
    "prompt": "为 API 端点 /users 编写单元测试"
  }
}
```

**Task 工具执行流程：**
```python
class Task(BaseTool):
    async def execute(self, agent: str, prompt: str):
        # 1. 从 LaborMarket 获取子 Agent
        subagent = self._runtime.labor_market.get_subagent(agent)

        # 2. 创建新的 Soul（独立的上下文）
        sub_soul = KimiSoul(
            agent=subagent,
            context=Context(...)  # 新上下文
        )

        # 3. 运行子 Agent
        await sub_soul.run(prompt)

        # 4. 返回结果
        return ToolResult(output="子 Agent 执行结果...")
```

**关键特点：**
- 子 Agent 有独立的 `Context`，不影响父 Agent
- 子 Agent 也有自己的审批流程
- 子 Agent 也可以调用其他工具，包括再创建子 Agent

### 4.7 第五阶段：上下文压缩场景

假设经过多轮对话，token 数超过了阈值（85% 最大上下文）：

```python
# _agent_loop 中的检查
if should_auto_compact(
    self._context.token_count,      # 如 85000
    self._runtime.llm.max_context_size,  # 如 100000
    trigger_ratio=0.85,              # 阈值
):
    await self.compact_context()
```

**compact_context 执行：**

```python
async def compact_context(self):
    wire_send(CompactionBegin())  # UI 显示"正在压缩..."

    # 调用 SimpleCompaction
    compaction_result = await self._compaction.compact(
        self._context.history,
        self._runtime.llm,
        custom_instruction=""
    )

    # 清空当前上下文
    await self._context.clear()

    # 创建新检查点
    await self._checkpoint()

    # 添加压缩后的消息
    await self._context.append_message(compaction_result.messages)

    wire_send(CompactionEnd())
```

**压缩前后对比：**

```
压缩前（85000 tokens）:
[
    SystemMessage("..."),
    UserMessage("任务1...", checkpoint_id=0),
    AssistantMessage("我来...", tool_calls=[...]),
    ToolResultMessage(...),
    UserMessage("任务2...", checkpoint_id=1),
    AssistantMessage("好的...", tool_calls=[...]),
    ToolResultMessage(...),
    # ... 50+ 条消息
    UserMessage("当前任务...", checkpoint_id=10),
]

压缩后（约 20000 tokens）:
[
    SystemMessage("..."),
    UserMessage("""[之前对话的总结]

    用户要求分析项目代码结构。我已经完成了：
    1. 使用 Glob 找到所有 Python 文件
    2. 使用 Grep 识别 API 端点
    3. 发现 3 个主要端点: /users, /items, /orders

    当前任务: 为这些端点添加单元测试"""),
    UserMessage("当前任务...", checkpoint_id=11),
]
```

### 4.8 第六阶段：D-Mail 时间旅行场景

D-Mail（电话微波炉）是一个独特的功能，允许"时间旅行"回退到之前的检查点。

**场景：用户想要撤销一系列操作**

假设 AI 已经执行了多个步骤，但用户发现方向错了，想要回退到第 3 步：

```python
# 在工具内部（如 SendDMail）
async def execute(self, checkpoint_id: int, message: str):
    # 发送 D-Mail 到过去的检查点
    self._denwa_renji.send_dmail(
        checkpoint_id=3,  # 回到第 3 个检查点
        message="请改用 pytest 而不是 unittest"
    )
    return ToolResult(output="D-Mail sent")
```

**D-Mail 处理流程：**

```python
# _step 中的检查
if dmail := self._denwa_renji.fetch_pending_dmail():
    # 抛出 BackToTheFuture 异常
    raise BackToTheFuture(
        checkpoint_id=dmail.checkpoint_id,  # 3
        messages=[
            Message(
                role="user",
                content=[
                    system("You just got a D-Mail from your future self...")
                ]
            )
        ]
    )
```

**_agent_loop 捕获异常：**

```python
except BackToTheFuture as e:
    back_to_the_future = e

# 在循环末尾处理
if back_to_the_future is not None:
    # 1. 回退上下文到检查点 3
    await self._context.revert_to(back_to_the_future.checkpoint_id)

    # 2. 创建新检查点
    await self._checkpoint()

    # 3. 添加 D-Mail 消息
    await self._context.append_message(back_to_the_future.messages)

    # 4. 继续循环（从检查点 3 重新开始）
```

**上下文变化：**
```
原始:
[Msg1, Msg2, Msg3(checkpoint=3), Msg4, Msg5, Msg6, Msg7]

收到 D-Mail 回到 checkpoint=3:
    ↓
revert_to(3):
[Msg1, Msg2, Msg3(checkpoint=3)]

添加 D-Mail:
[Msg1, Msg2, Msg3(checkpoint=3), D-Mail("请改用 pytest...")]

下一轮循环从 Msg3 之后继续执行
```

### 4.9 第七阶段：Step 结束判断

```python
    if step_outcome is not None:
        # 消费 steer 消息（实时干预）
        has_steers = await self._consume_pending_steers()

        if step_outcome.stop_reason == "no_tool_calls" and has_steers:
            continue  # 有 steer 消息，强制继续

        # 回合结束
        return TurnOutcome(
            stop_reason=step_outcome.stop_reason,
            final_message=step_outcome.assistant_message,
            step_count=step_no,
        )
```

**停止条件：**

| 条件 | 说明 |
|------|------|
| `no_tool_calls` | AI 没有调用工具，自然结束 |
| `tool_rejected` | 用户拒绝了工具操作 |
| `max_steps_reached` | 达到最大步数限制 |

### 4.10 完整执行流程图

```
用户输入: "帮我分析项目代码结构..."
    ↓
KimiSoul.run()
    ↓
┌─────────────────────────────────────────┐
│ 不是斜杠命令 → _turn()                   │
├─────────────────────────────────────────┤
│ 1. checkpoint() 创建检查点 0             │
│ 2. append_message() 添加用户消息         │
│ 3. _agent_loop() 进入核心循环            │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Step 1                                  │
├─────────────────────────────────────────┤
│ 检查: token > 85%? → 否                 │
│ _step():                                │
│   - kosong.step() 调用 LLM              │
│   - LLM 输出: tool_calls=[Glob, Grep]   │
│   - 并行执行工具                         │
│   - _grow_context() 添加结果             │
│ 返回: None (有 tool_calls，继续)         │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Step 2                                  │
├─────────────────────────────────────────┤
│ _step():                                │
│   - kosong.step() 调用 LLM              │
│   - LLM 输出: tool_calls=[ReadFile x3]  │
│   - 读取文件内容...                      │
│   - _grow_context() 添加结果             │
│ 返回: None (有 tool_calls，继续)         │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Step 3                                  │
├─────────────────────────────────────────┤
│ 检查: token > 85%? → 是                 │
│ compact_context() 压缩上下文             │
│ _step():                                │
│   - LLM 输出: "分析完成，发现3个端点"    │
│   - 无 tool_calls                        │
│ 返回: StepOutcome("no_tool_calls")      │
└─────────────────────────────────────────┘
    ↓
_agent_loop 返回 TurnOutcome
    ↓
run() 发送 TurnEnd()
    ↓
回合结束，等待用户下一步输入
```

---

## 五、上下文管理与压缩

### 4.1 上下文组织

#### 4.1.1 消息类型

```python
# 基础消息类型
class Message(ABC):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[ContentPart]

# 具体消息类型
class SystemMessage(Message):
    role = "system"

class UserMessage(Message):
    role = "user"
    checkpoint_id: int | None  # 关联的检查点

class AssistantMessage(Message):
    role = "assistant"
    tool_calls: list[ToolCall] | None

class ToolResultMessage(Message):
    role = "tool"
    tool_call_id: str
```

#### 4.1.2 上下文结构

```python
class Context:
    _history: list[Message] = [
        # 系统提示词（始终保留）
        SystemMessage(content="..."),

        # 用户消息
        UserMessage(content="你好"),

        # Assistant 回复
        AssistantMessage(content="你好！有什么可以帮助你？"),

        # 工具调用示例
        AssistantMessage(
            content=None,
            tool_calls=[ToolCall(id="1", name="ReadFile", arguments='{"path": "test.py"}')]
        ),
        ToolResultMessage(
            tool_call_id="1",
            content="def hello():\n    print('hello')"
        ),

        # 更多交互...
    ]
```

#### 4.1.3 检查点机制

检查点用于 D-Mail（时间旅行）功能，允许回退到特定状态：

```python
async def checkpoint(self, add_user_message: bool = True):
    """创建检查点"""
    checkpoint_id = self._next_checkpoint_id
    self._next_checkpoint_id += 1

    if add_user_message:
        # 添加用户消息并关联检查点
        user_msg = UserMessage(
            content="...",
            checkpoint_id=checkpoint_id
        )
        self._history.append(user_msg)

    # 持久化到文件
    await self._persist()

    return checkpoint_id

async def revert_to(self, checkpoint_id: int):
    """回退到指定检查点"""
    # 找到检查点位置
    for i, msg in enumerate(self._history):
        if isinstance(msg, UserMessage) and msg.checkpoint_id == checkpoint_id:
            # 截断历史到检查点
            self._history = self._history[:i+1]
            break

    # 重新计算 token 数
    self._token_count = await self._count_tokens()
    await self._persist()
```

### 4.2 上下文压缩

#### 4.2.1 压缩触发条件

```python
def should_auto_compact(
    token_count: int,
    max_context_size: int,
    trigger_ratio: float = 0.85,
    reserved_context_size: int = 50000,
) -> bool:
    """
    判断是否需要进行上下文压缩

    触发条件：
    1. Token 数超过最大上下文的 85%（默认）
    2. Token 数 + 预留空间 >= 最大上下文
    """
    return (
        token_count >= max_context_size * trigger_ratio
        or token_count + reserved_context_size >= max_context_size
    )
```

#### 4.2.2 压缩策略

Kimi CLI 实现了两种压缩策略：

**1. SimpleCompaction（简单压缩）**

```python
class SimpleCompaction:
    """简单压缩：总结旧消息，保留最近的消息"""

    async def compact(self, context: Context) -> Context:
        # 1. 保留系统提示词
        system_message = context.history[0]

        # 2. 保留最近 N 条消息（不压缩）
        recent_messages = context.history[-self.keep_recent:]

        # 3. 中间的消息进行总结
        old_messages = context.history[1:-self.keep_recent]
        summary = await self._summarize(old_messages)

        # 4. 构建新的上下文
        new_history = [
            system_message,
            UserMessage(content=f"[之前对话的总结]\n{summary}"),
            *recent_messages
        ]

        return Context(history=new_history)
```

**2. 压缩实现细节**

```python
async def compact_context(self):
    """执行上下文压缩"""
    logger.info(f"Compacting context: {self._context.token_count()} tokens")

    # 创建压缩器
    compactor = SimpleCompaction(
        llm=self._runtime.llm,
        keep_recent=4,  # 保留最近 4 条消息
    )

    # 执行压缩
    compacted = await compactor.compact(self._context)

    # 替换上下文
    self._context = compacted

    logger.info(f"Compaction complete: {self._context.token_count()} tokens")
```

#### 4.2.3 压缩流程图

```
┌─────────────────────────────────────────────────────────────┐
│                      上下文压缩流程                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  原始上下文（超过阈值）                                        │
│  ┌─────────┬──────────┬──────────┬──────────┬──────────┐    │
│  │ System  │  Old_1   │  Old_2   │  ...     │  Recent  │    │
│  │ Prompt  │          │          │          │  4 msgs  │    │
│  └────┬────┴────┬─────┴─────┬────┴─────┬────┴─────┬────┘    │
│       │         │           │          │          │         │
│       │         └───────────┴──────────┘          │         │
│       │                    │                      │         │
│       │                    ▼                      │         │
│       │            ┌───────────────┐              │         │
│       │            │   总结旧消息   │              │         │
│       │            │  (LLM 调用)   │              │         │
│       │            └───────┬───────┘              │         │
│       │                    │                      │         │
│       │                    ▼                      │         │
│       │            ┌───────────────┐              │         │
│       │            │    Summary    │              │         │
│       │            └───────┬───────┘              │         │
│       │                    │                      │         │
│       └────────────────────┼──────────────────────┘         │
│                            │                                │
│                            ▼                                │
│  压缩后上下文                                                │
│  ┌─────────┬──────────┬──────────┬──────────┬──────────┐    │
│  │ System  │ Summary  │ Recent_1 │ Recent_2 │ Recent_3 │    │
│  │ Prompt  │          │          │          │ Recent_4 │    │
│  └─────────┴──────────┴──────────┴──────────┴──────────┘    │
│                                                              │
│  结果：token 数量显著减少，保留关键信息                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、系统提示词

### 5.1 系统提示词结构

系统提示词使用 **Jinja2 模板** 渲染，位于 `src/kimi_cli/agents/`：

```
agents/
├── default/
│   ├── agent.yaml       # Agent 配置
│   └── system.md        # 系统提示词模板
├── coder/
│   ├── agent.yaml
│   └── system.md
└── ...
```

### 5.2 默认系统提示词结构

```markdown
# 角色定义

你是 Kimi，一个 AI 编程助手。

## 核心能力

- 编写、读取、修改代码
- 执行 Shell 命令
- 搜索网络信息
- 委派任务给子 Agent

## 工作原则

1. **先思考，后行动**
   - 面对复杂任务，先使用 Think 工具规划
   - 明确步骤后再执行

2. **文件操作规范**
   - 读取文件时使用 ReadFile 工具
   - 修改文件时使用 StrReplaceFile 工具
   - 写入新文件时使用 WriteFile 工具

3. **工具使用规范**
   - 每次可以调用多个工具
   - 等待工具执行结果后再继续
   - 工具调用失败时分析原因并重试

## 环境信息

- 操作系统: {{ os }}
- Shell: {{ shell }}
- 工作目录: {{ work_dir }}

## 可用工具

{% for tool in tools %}
### {{ tool.name }}

{{ tool.description }}

参数:
```json
{{ tool.parameters }}
```

{% endfor %}

## 子 Agent

{% for name, subagent in subagents.items() %}
- **{{ name }}**: {{ subagent.description }}
{% endfor %}

当任务适合特定子 Agent 时，使用 Task 工具委派。

{{ ROLE_ADDITIONAL }}
```

### 5.3 提示词渲染

```python
async def _load_system_prompt(
    agent_spec: AgentSpec,
    runtime: Runtime,
) -> str:
    """加载并渲染系统提示词"""
    # 1. 读取模板文件
    template_path = agent_spec.system_prompt_path
    template_content = await template_path.read_text()

    # 2. 准备渲染参数
    template_args = {
        # 基础信息
        "os": runtime.environment.os,
        "shell": runtime.environment.shell,
        "work_dir": str(runtime.session.work_dir),

        # 工具信息
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in toolset.get_tools()
        ],

        # 子 Agent 信息
        "subagents": {
            name: {"description": subagent.description}
            for name, subagent in runtime.labor_market.get_subagents().items()
        },

        # 自定义参数
        **agent_spec.system_prompt_args,
    }

    # 3. 渲染模板
    template = jinja2.Template(template_content)
    system_prompt = template.render(**template_args)

    return system_prompt
```

### 5.4 动态提示词内容

系统提示词包含动态生成的内容：

| 动态内容 | 说明 |
|---------|------|
| **环境信息** | OS、Shell、工作目录 |
| **工具列表** | 当前 Agent 可用的所有工具及其参数定义 |
| **子 Agent** | 可用的子 Agent 及其描述 |
| **Skills** | 已加载的 Skills |
| **自定义参数** | YAML 中定义的 `system_prompt_args` |

### 5.5 提示词示例

**渲染后的系统提示词片段**:

```markdown
# 角色定义

你是 Kimi，一个 AI 编程助手。

## 环境信息

- 操作系统: Darwin
- Shell: /bin/zsh
- 工作目录: /Users/louishsu/project

## 可用工具

### ReadFile

读取文件内容，支持指定行范围。

参数:
```json
{
  "file_path": {"type": "string", "description": "文件路径"},
  "offset": {"type": "integer", "description": "起始行号"},
  "limit": {"type": "integer", "description": "读取行数"}
}
```

### Shell

执行 Shell 命令。

参数:
```json
{
  "command": {"type": "string", "description": "命令"},
  "timeout": {"type": "integer", "description": "超时时间(秒)"}
}
```

## 子 Agent

- **coder**: 擅长编写和重构代码
- **tester**: 擅长编写测试用例
```

---

## 七、工具系统详解

### 6.1 工具基类

```python
class BaseTool(BaseModel):
    """工具基类"""
    name: str
    description: str
    parameters: dict  # JSON Schema

    async def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        raise NotImplementedError
```

### 6.2 工具执行流程

```
┌─────────────────────────────────────────────────────────────┐
│                        工具执行流程                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  LLM 输出工具调用                                              │
│  ┌──────────────────────────────────────┐                   │
│  │ ToolCall(                             │                   │
│  │   id="1",                             │                   │
│  │   name="ReadFile",                    │                   │
│  │   args='{"file_path": "test.py"}'     │                   │
│  │ )                                     │                   │
│  └──────────────┬───────────────────────┘                   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────────────────┐                   │
│  │ 1. 查找对应工具                        │                   │
│  │    tool = toolset.get("ReadFile")     │                   │
│  └──────────────┬───────────────────────┘                   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────────────────┐                   │
│  │ 2. 验证参数                            │                   │
│  │    jsonschema.validate(args, schema)  │                   │
│  └──────────────┬───────────────────────┘                   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────────────────┐                   │
│  │ 3. 请求审批（如需）                     │                   │
│  │    if tool.needs_approval:            │                   │
│  │        approved = await approval.request(...)           │
│  └──────────────┬───────────────────────┘                   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────────────────┐                   │
│  │ 4. 执行工具                            │                   │
│  │    result = await tool.execute(**args)                  │
│  └──────────────┬───────────────────────┘                   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────────────────┐                   │
│  │ 5. 返回结果                            │                   │
│  │    ToolResult(                        │                   │
│  │      output="...",                    │                   │
│  │      error=None                       │                   │
│  │    )                                  │                   │
│  └──────────────────────────────────────┘                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 八、总结

### 7.1 核心设计思想

1. **分层架构**: UI 层、协议层、核心层分离，职责清晰
2. **不可变 Agent**: Agent 配置不可变，确保安全性
3. **上下文管理**: 检查点 + 压缩，平衡历史记录和 Token 限制
4. **时间旅行**: D-Mail 机制支持任务回滚，增强容错能力
5. **依赖注入**: Runtime 作为依赖容器，便于测试和扩展

### 7.2 关键组件关系

```
KimiCLI (入口)
    │
    ├── Config (配置中心)
    │
    ├── Runtime (执行上下文)
    │       ├── Session (会话)
    │       ├── Approval (审批)
    │       ├── LaborMarket (子 Agent)
    │       └── DenwaRenji (D-Mail)
    │
    ├── Agent (配置实体)
    │       ├── system_prompt (系统提示词)
    │       └── toolset (工具集)
    │
    ├── KimiSoul (主循环)
    │       ├── _agent_loop (Agent 循环)
    │       ├── _step (单步执行)
    │       └── compact_context (上下文压缩)
    │
    ├── Context (消息上下文)
    │       ├── _history (消息历史)
    │       ├── checkpoint (检查点)
    │       └── revert_to (回滚)
    │
    └── Wire (通信协议)
            ├── soul_side (发送端)
            └── ui_side (接收端)
```

Kimi Code CLI 是一个架构清晰、设计精良的 AI Agent CLI 工具，值得深入学习。
