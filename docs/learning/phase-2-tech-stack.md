# 阶段二：技术栈基础补齐 — AgentHub 深度学习指南

> **学习目标**：掌握 AgentHub 用到的核心技术栈，为后续阅读代码做准备。
> 本文档按优先级从高到低排列，每个技术都配合项目实际代码示例。
> 预计耗时 3-5 天（每天 2-3 小时）。

---

## 目录

1. [技术栈优先级总览](#1-技术栈优先级总览)
2. [Python + FastAPI：后端框架](#2-python--fastapi后端框架)
3. [SQLAlchemy 2.0：ORM 与数据访问](#3-sqlalchemy-20orm-与数据访问)
4. [asyncio：Python 异步编程](#4-asynciopython-异步编程)
5. [Pydantic v2：数据验证与序列化](#5-pydantic-v2数据验证与序列化)
6. [Next.js 16 App Router：前端框架](#6-nextjs-16-app-router前端框架)
7. [React 19 + TypeScript：组件开发](#7-react-19--typescript组件开发)
8. [Zustand + Immer：状态管理](#8-zustand--immer状态管理)
9. [SSE (Server-Sent Events)：实时通信](#9-sse-server-sent-events实时通信)
10. [Tailwind CSS + shadcn/ui：样式与组件](#10-tailwind-css--shadcnui样式与组件)
11. [技术映射对照表](#11-技术映射对照表)
12. [自检清单](#12-自检清单)

---

## 1. 技术栈优先级总览

| 优先级 | 技术 | 原因 | 建议投入 |
|--------|------|------|---------|
| **最高** | Python + FastAPI | 后端 100% 业务逻辑 | 2 天 |
| **最高** | SQLAlchemy 2.0 async | 数据层核心 | 1 天 |
| **高** | asyncio | 理解并发和流式处理 | 1 天 |
| **高** | Pydantic v2 | 所有数据验证和序列化 | 0.5 天 |
| **中** | Next.js 16 App Router | 前端入口和布局 | 0.5 天 |
| **中** | React 19 + TypeScript | UI 组件开发 | 1 天 |
| **中** | Zustand + Immer | 前端状态管理 | 0.5 天 |
| **中** | SSE | 理解实时通信机制 | 0.5 天 |
| **低** | Tailwind + shadcn/ui | 样式（可读代码时现学） | 随用随学 |

### 学习策略

- **后端优先**：AgentHub 的核心业务逻辑全在 Python 后端，前端只做展示
- **带着项目学**：每个技术都配合项目实际代码理解，不学无关特性
- **够用就好**：不需要精通每个技术的全部特性，掌握项目用到的子集即可

---

## 2. Python + FastAPI：后端框架

> **为什么最重要**：AgentHub 后端 100% 用 Python + FastAPI 编写，所有业务逻辑（Agent 执行、消息处理、工具系统、Orchestrator 调度）都在这里。

### FastAPI 核心概念（5 分钟理解）

FastAPI 是一个现代的 Python Web 框架，特点：
- **类型提示驱动**：用 Python 的类型提示自动生成 API 文档和验证
- **异步原生**：所有路由都支持 `async def`
- **自动 OpenAPI 文档**：启动后访问 `/docs` 即可看到交互式 API 文档

### 项目入口分析

```python
# backend/app/main.py（节选）
from fastapi import FastAPI
from contextlib import asynccontextmanager

# 1. Lifespan 生命周期管理器
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用启动时执行，关闭时清理"""
    # 启动时：加载环境变量、初始化数据库
    apply_env_overrides()
    import app.services.agent_runner  # 触发模块加载
    await init_db()
    yield  # ← 应用运行中
    # 关闭时：清理资源
    await close_db()

# 2. 创建 FastAPI 应用
def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentHub Backend",
        lifespan=lifespan,  # 绑定生命周期
    )
    
    # 3. 添加中间件（CORS）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],  # 允许前端跨域
        allow_methods=["*"],
    )
    
    # 4. 注册路由（Router）
    app.include_router(conversations.router, prefix="/api", tags=["conversations"])
    app.include_router(messages.router, prefix="/api", tags=["messages"])
    app.include_router(stream.router, prefix="/api", tags=["stream"])
    # ... 更多路由
    
    return app

app = create_app()
```

### 路由定义模式（项目实际写法）

```python
# backend/app/api/conversations.py（简化示例）
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.engine import get_db_session

router = APIRouter()

@router.get("/conversations")
async def list_conversations(
    session: AsyncSession = Depends(get_db_session)  # 依赖注入
) -> list[dict]:
    """列出所有会话"""
    # 查询数据库...
    return conversations

@router.post("/conversations/{conv_id}/messages")
async def send_message(
    conv_id: str,
    body: SendMessageRequest,  # Pydantic 模型自动验证请求体
    session: AsyncSession = Depends(get_db_session)
) -> dict:
    """发送消息"""
    # 业务逻辑...
    return {"messageId": msg_id}
```

### 你需要掌握的 FastAPI 特性

| 特性 | 项目用法 | 学习要点 |
|------|---------|---------|
| **路由装饰器** | `@router.get()`, `@router.post()` | 理解 HTTP 方法和路径参数 |
| **依赖注入** | `Depends(get_db_session)` | 理解如何获取数据库 session |
| **请求验证** | Pydantic 模型作为参数类型 | 自动验证请求体 |
| **路径参数** | `/conversations/{conv_id}` | 从 URL 提取参数 |
| **异步路由** | `async def` | 非阻塞 I/O |
| **CORS** | `CORSMiddleware` | 前后端分离必须配置 |

### 快速上手练习

1. 启动后端，访问 `http://localhost:8000/docs` 查看自动生成的 API 文档
2. 在文档界面直接测试 `GET /api/conversations` 接口
3. 阅读 `backend/app/api/` 目录下的路由文件，理解 API 结构

---

## 3. SQLAlchemy 2.0：ORM 与数据访问

> **为什么重要**：AgentHub 的所有数据持久化都用 SQLAlchemy 2.0，理解它才能读懂数据层代码。

### SQLAlchemy 2.0 核心概念

SQLAlchemy 是 Python 最流行的 ORM，2.0 版本引入了：
- **声明式映射**：用类定义表结构
- **类型安全**：`Mapped[]` 类型提示
- **异步支持**：`AsyncSession` + `asyncio`

### 项目模型定义（实际代码）

```python
# backend/app/db/models.py（节选）
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Text, Boolean, ForeignKey

class Base(DeclarativeBase):
    """所有模型的基类"""
    pass

class Agent(Base):
    __tablename__ = "agents"
    
    # 主键
    id: Mapped[str] = mapped_column(String, primary_key=True)
    
    # 必填字段
    name: Mapped[str] = mapped_column(String, nullable=False)
    system_prompt: Mapped[str] = mapped_column(String, name="system_prompt", nullable=False)
    adapter_name: Mapped[str] = mapped_column(String, name="adapter_name", nullable=False)
    
    # 可选字段
    api_key: Mapped[str | None] = mapped_column(String, name="api_key", nullable=True)
    
    # JSON 字段（SQLite 没有原生 JSON 类型，存为 Text）
    capabilities: Mapped[str] = mapped_column(Text, default="[]")
    tool_names: Mapped[str] = mapped_column(Text, name="tool_names", default="[]")
    
    # 布尔字段
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_orchestrator: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # 时间戳（用整数毫秒，不用 datetime）
    created_at: Mapped[int] = mapped_column(Integer, name="created_at", nullable=False)
    
    # 关系
    messages: Mapped[list["Message"]] = relationship(back_populates="agent")
    
    # JSON 字段的 Python 属性访问器
    @property
    def capabilities_list(self) -> list[str]:
        return json.loads(self.capabilities) or []

class Message(Base):
    __tablename__ = "messages"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("conversations.id", ondelete="CASCADE"),  # 级联删除
        nullable=False,
    )
    parts: Mapped[str] = mapped_column(Text, default="[]")  # JSON 存 MessagePart 数组
    
    # 索引定义
    __table_args__ = (
        Index("idx_messages_conv_created", "conversation_id", "created_at"),
    )
```

### 数据库引擎配置（实际代码）

```python
# backend/app/db/engine.py（节选）
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession,
    async_sessionmaker, create_async_engine
)

async def init_db() -> None:
    # 1. 创建异步引擎
    engine = create_async_engine(
        "sqlite+aiosqlite:///../.agenthub-data/agenthub.db",
        echo=False,  # 生产环境不打印 SQL
    )
    
    # 2. SQLite 特殊配置（每个连接都要设置）
    @event.listens_for(engine.sync_engine, "connect")
    def _init_sqlite_connection(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")      # 启用外键级联
        cursor.execute("PRAGMA journal_mode=WAL")      # WAL 模式（并发读写）
        cursor.execute("PRAGMA busy_timeout=5000")     # 等锁 5 秒
        cursor.close()
    
    # 3. 创建 session 工厂
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,  # 提交后不刷新属性
        autoflush=False,         # 不自动 flush
    )
    
    # 4. 自动建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### 数据库 Session 使用模式

```python
# 作为上下文管理器使用
@asynccontextmanager
async def get_db() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()   # 正常退出时提交
        except Exception:
            await session.rollback() # 异常时回滚
            raise

# 作为 FastAPI 依赖注入
async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_db() as session:
        yield session
```

### 你需要掌握的 SQLAlchemy 特性

| 特性 | 项目用法 | 学习要点 |
|------|---------|---------|
| **声明式模型** | `class Agent(Base)` | 理解类和表的映射 |
| **类型映射** | `Mapped[str]`, `Mapped[int]` | 理解字段类型 |
| **外键关系** | `ForeignKey("conversations.id", ondelete="CASCADE")` | 理解级联删除 |
| **relationship** | `relationship(back_populates="...")` | 理解双向关系 |
| **异步查询** | `AsyncSession` + `select()` | 理解异步数据库操作 |
| **JSON 字段** | `Text` + `json.loads/dumps` | SQLite 没有原生 JSON |

### SQLite 特殊配置（重要！）

项目使用 SQLite，需要注意：

| PRAGMA | 作用 | 为什么需要 |
|--------|------|-----------|
| `foreign_keys=ON` | 启用外键约束 | 默认关闭，不启用则级联删除不生效 |
| `journal_mode=WAL` | Write-Ahead Logging | 允许并发读 + 单写，提高性能 |
| `busy_timeout=5000` | 等锁 5 秒 | 避免 "database is locked" 错误 |

---

## 4. asyncio：Python 异步编程

> **为什么重要**：AgentHub 后端大量使用异步编程，理解它才能读懂并发代码（Agent 执行、SSE 推送、工具并发调用）。

### asyncio 核心概念

```
同步代码（阻塞）    vs    异步代码（非阻塞）
─────────────────       ─────────────────
def fetch():              async def fetch():
    result = db.query()       result = await db.query()
    return result             return result
    
# 阻塞等待                 # 等待时可以执行其他任务
```

### 项目中的 asyncio 用法

#### 1. async generator（异步生成器）

```python
# Adapter 返回事件流用的就是 async generator
class MockAdapter:
    async def stream(self, input, signal) -> AsyncIterator[StreamEvent]:
        """async generator：每 yield 一个事件，调用方可以处理后再要下一个"""
        for event in self.scripts.get(input.agent_id, DEFAULT_SCRIPT):
            if signal.is_set():  # 检查是否被中止
                return
            await asyncio.sleep(0.05)  # 模拟延迟
            yield event  # ← yield 出一个事件
```

#### 2. asyncio.Task（并发任务）

```python
# AgentRunner 启动 Agent 执行（不阻塞）
async def run(agent_id: str, ...):
    # 创建异步任务，立即返回，不等待完成
    task = asyncio.create_task(execute_run(agent_id, ...))
    return task

# Orchestrator 并行执行多个子任务
async def execute_plan(plan: list[DispatchPlanItem]):
    # 同一波次的任务并行执行
    results = await asyncio.gather(
        *[run_sub_task(task) for task in ready_tasks]
    )
```

#### 3. asyncio.Event（事件信号）

```python
# 中止信号使用 asyncio.Event
class ToolContext:
    abort_signal: asyncio.Event  # 替代 JS 的 AbortSignal

# 工具执行时检查是否被中止
async def bash_handler(args, ctx):
    process = subprocess.Popen(...)
    
    # 等待进程完成或被中止
    done, pending = await asyncio.wait(
        [asyncio.create_task(wait_for_process(process)),
         asyncio.create_task(wait_for_event(ctx.abort_signal))],
        return_when=asyncio.FIRST_COMPLETED
    )
    
    if ctx.abort_signal.is_set():
        process.kill()  # 被中止，杀掉进程
```

#### 4. asyncio.Queue（队列）

```python
# EventBus 使用 Queue 实现事件扇出
class EventBus:
    def __init__(self):
        self.subscribers: list[asyncio.Queue] = []
    
    def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.subscribers.append(queue)
        return queue
    
    async def publish(self, event: StreamEvent):
        for queue in self.subscribers:
            await queue.put(event)  # 每个订阅者都收到事件
```

### 你需要掌握的 asyncio 特性

| 特性 | 项目用法 | 学习要点 |
|------|---------|---------|
| **async/await** | 几乎所有函数 | 理解异步函数定义和调用 |
| **async generator** | `Adapter.stream()` | 理解 `async for` 和 `yield` |
| **asyncio.Task** | `create_task()`, `gather()` | 理解并发执行 |
| **asyncio.Event** | 中止信号 | 理解事件信号机制 |
| **asyncio.Queue** | EventBus | 理解生产者-消费者模式 |
| **asyncio.wait** | 等待多个任务 | 理解 `FIRST_COMPLETED` |

### 同步 vs 异步对照

| JavaScript | Python | 说明 |
|-----------|--------|------|
| `async function` | `async def` | 异步函数定义 |
| `await promise` | `await coroutine` | 等待异步结果 |
| `Promise.all()` | `asyncio.gather()` | 并发执行 |
| `AbortSignal` | `asyncio.Event` | 中止信号 |
| `EventEmitter` | `asyncio.Queue` | 事件发布/订阅 |
| `AsyncIterable` | `async generator` | 异步迭代器 |

---

## 5. Pydantic v2：数据验证与序列化

> **为什么重要**：AgentHub 用 Pydantic 替代了 TypeScript 的 Zod，所有数据验证和 JSON 序列化都在这里。

### Pydantic 核心概念

Pydantic 是 Python 的数据验证库，特点：
- **类型提示驱动**：用 Python 类型提示定义 schema
- **自动验证**：实例化时自动验证数据
- **序列化**：自动转换为 JSON/dict

### 项目中的 Pydantic 用法

#### 1. 请求/响应模型

```python
# backend/app/schemas/requests.py（简化示例）
from pydantic import BaseModel, Field

class SendMessageRequest(BaseModel):
    """发送消息的请求体"""
    content: str = Field(min_length=1, description="消息内容")
    mentioned_agent_ids: list[str] = Field(default=[], alias="mentionedAgentIds")
    attachments: list[str] = Field(default=[])
    
    model_config = {"populate_by_name": True}  # 允许用 snake_case 或 camelCase
```

#### 2. StreamEvent 事件模型

```python
# backend/app/schemas/events.py（实际代码）
from pydantic import BaseModel, Field
from typing import Literal, Union, Annotated

class BaseEvent(BaseModel):
    """所有事件的基类"""
    conversation_id: str = Field(alias="conversationId")  # camelCase 别名
    timestamp: int
    
    model_config = {"populate_by_name": True}  # 允许两种命名

class RunStartEvent(BaseEvent):
    type: Literal["run.start"] = "run.start"  # 字面量类型
    run_id: str = Field(alias="runId")
    agent_id: str = Field(alias="agentId")
    trigger_message_id: str = Field(alias="triggerMessageId")
    parent_run_id: str | None = Field(default=None, alias="parentRunId")

class PartDeltaEvent(BaseEvent):
    type: Literal["part.delta"] = "part.delta"
    message_id: str = Field(alias="messageId")
    part_index: int = Field(alias="partIndex")
    delta: dict  # 增量内容

# 可辨识联合（Discriminated Union）
StreamEvent = Annotated[
    Union[RunStartEvent, RunEndEvent, PartDeltaEvent, ...],
    Field(discriminator="type"),  # 按 type 字段区分
]
```

#### 3. 配置管理

```python
# backend/app/config.py（实际代码）
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """从环境变量和 .env 文件加载配置"""
    model_config = SettingsConfigDict(
        env_file=".env",           # 读取 .env 文件
        env_file_encoding="utf-8",
        case_sensitive=False,      # 环境变量不区分大小写
        extra="ignore",            # 忽略多余的字段
    )
    
    # 数据库
    database_url: str = "sqlite+aiosqlite:///../.agenthub-data/agenthub.db"
    
    # API Keys（可选）
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    
    # 服务器配置
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    
    # 计算属性
    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

# 使用 @lru_cache 缓存，只加载一次
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### snake_case vs camelCase（重要！）

项目使用 **snake_case 字段 + camelCase 别名**，保持与前端 JSON 兼容：

```python
class RunStartEvent(BaseModel):
    run_id: str = Field(alias="runId")  # Python 用 run_id，JSON 用 runId
    
    model_config = {"populate_by_name": True}

# 创建时可以用两种命名
event1 = RunStartEvent(run_id="run_001", ...)  # snake_case
event2 = RunStartEvent(runId="run_001", ...)   # camelCase

# 序列化时输出 camelCase（与前端兼容）
event1.model_dump(by_alias=True)
# → {"runId": "run_001", ...}
```

### 你需要掌握的 Pydantic 特性

| 特性 | 项目用法 | 学习要点 |
|------|---------|---------|
| **BaseModel** | 所有 schema 的基类 | 理解模型定义 |
| **Field** | `Field(alias="...", default=...)` | 理解字段配置 |
| **Literal** | `type: Literal["run.start"]` | 字面量类型 |
| **Union + discriminator** | StreamEvent 联合类型 | 可辨识联合 |
| **BaseSettings** | 配置管理 | 从环境变量加载 |
| **populate_by_name** | 允许两种命名 | snake/camel 兼容 |

---

## 6. Next.js 16 App Router：前端框架

> **为什么中等优先级**：前端入口和布局用 Next.js，但核心逻辑都在后端，前端主要是展示层。

### Next.js App Router 核心概念

Next.js 16 使用 **App Router**（不是 Pages Router），特点：
- **文件系统路由**：`src/app/` 目录结构即路由结构
- **Server Components**：默认在服务端渲染
- **Client Components**：`'use client'` 标记客户端组件

### 项目结构

```
src/app/
├── layout.tsx     # 根布局（全局 Provider 在这里挂载）
├── page.tsx       # 首页（挂载主界面组件）
├── globals.css    # 全局样式
└── favicon.ico
```

**注意**：项目当前没有 `src/app/api/` 目录，所有 API 都指向独立的 Python 后端。

### layout.tsx（根布局）

```tsx
// src/app/layout.tsx（简化示例）
import { StreamProvider } from '@/components/stream-provider'
import { ThemeProvider } from '@/components/theme-provider'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh" suppressHydrationWarning>
      <body>
        <ThemeProvider>           {/* 主题管理 */}
          <StreamProvider>        {/* SSE 全局连接 */}
            {children}            {/* 页面内容 */}
          </StreamProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
```

### page.tsx（首页）

```tsx
// src/app/page.tsx（简化示例）
'use client'  // ← 标记为客户端组件

import { Sidebar } from '@/components/sidebar'
import { ChatPanel } from '@/components/chat-panel'

export default function Home() {
  return (
    <main className="flex h-screen">
      <Sidebar />       {/* 左侧：会话列表/产物库/Agent 库 */}
      <ChatPanel />     {/* 中间：聊天面板 */}
      {/* 右侧：产物预览面板（条件渲染） */}
    </main>
  )
}
```

### 'use client' 指令（重要！）

```tsx
// 服务端组件（默认）
// - 在服务端渲染
// - 不能访问浏览器 API
// - 不能使用 useState/useEffect
export default function ServerComponent() { ... }

// 客户端组件（需要 'use client'）
'use client'
// - 在客户端运行
// - 可以使用所有 React hooks
// - 可以访问浏览器 API
export function ClientComponent() {
  const [state, setState] = useState(...)  // ✅
  useEffect(() => { ... })                  // ✅
}
```

项目大部分组件都是客户端组件（`'use client'`），因为需要：
- 访问 Zustand store
- 接收 SSE 事件
- 处理用户交互

---

## 7. React 19 + TypeScript：组件开发

> **为什么中等优先级**：所有 UI 组件都用 React + TypeScript，但如果你已有基础，可以快速上手。

### 项目组件模式

#### 1. 函数组件 + Hooks

```tsx
// src/components/message-item.tsx（简化示例）
'use client'

import { memo } from 'react'
import type { MessageRow } from '@/db/schema'

interface MessageItemProps {
  message: MessageRow
  isStreaming: boolean
}

export const MessageItem = memo(function MessageItem({ message, isStreaming }: MessageItemProps) {
  // 从 store 获取 agent 信息
  const agent = useAppStore((s) => s.agents[message.agentId ?? ''])
  
  return (
    <div className="flex gap-3">
      <AgentAvatar agent={agent} />
      <div className="flex-1">
        <MessageParts parts={message.parts} />
      </div>
    </div>
  )
})
```

#### 2. TypeScript 类型定义

```typescript
// src/shared/types.ts（节选）

// 可辨识联合类型
type MessagePart =
  | { type: 'text'; content: string }
  | { type: 'code'; language: string; content: string }
  | { type: 'thinking'; content: string }
  | { type: 'tool_use'; callId: string; toolName: string; args: unknown }
  | { type: 'tool_result'; callId: string; result: unknown; isError: boolean }
  | { type: 'artifact_ref'; artifactId: string }
  // ...

// 接口定义
interface StreamEvent {
  type: string
  conversationId: string
  timestamp: number
  // ...
}

// 字面量联合类型
type MessageStatus = 'streaming' | 'complete' | 'error' | 'aborted'
```

### 你需要掌握的 React/TS 特性

| 特性 | 项目用法 | 学习要点 |
|------|---------|---------|
| **函数组件** | 所有组件 | 理解 props 和组件定义 |
| **useState/useEffect** | 客户端组件 | 理解状态和副作用 |
| **memo** | 性能优化 | 理解组件记忆化 |
| **TypeScript 联合类型** | MessagePart | 理解可辨识联合 |
| **接口定义** | StreamEvent | 理解接口和类型 |
| **泛型** | 较少使用 | 基础理解即可 |

---

## 8. Zustand + Immer：状态管理

> **为什么重要**：AgentHub 的前端状态管理核心，所有 SSE 事件都通过 Zustand store 应用到 UI。

### Zustand 核心概念

Zustand 是轻量级状态管理库，特点：
- **极简 API**：`create()` 一个函数搞定
- **不包裹 Provider**：直接用 hook 访问
- **选择性订阅**：只订阅需要的状态，避免不必要的重渲染

### 项目 Store 结构

```typescript
// src/stores/app-store.ts（实际代码）
'use client'

import { create } from 'zustand'
import { immer } from 'zustand/middleware/immer'
import type { StreamEvent, MessagePart } from '@/shared/types'

// 1. 定义状态接口
interface AppState {
  // 实体（normalized 存储，按 ID 索引）
  conversations: Record<string, ConversationWithMeta>
  agents: Record<string, AgentRow>
  messages: Record<string, MessageRow>
  artifacts: Record<string, ArtifactRow>
  
  // 关系（按会话分桶）
  messageIdsByConv: Record<string, string[]>
  
  // UI 状态
  activeConversationId: string | null
  previewArtifactId: string | null
  
  // 审批队列
  pendingWritesByConv: Record<string, PendingWrite[]>
  
  // Actions
  applyEvent: (event: StreamEvent) => void  // ← 核心：应用 SSE 事件
  setActiveConversation: (id: string | null) => void
  // ...
}

// 2. 创建 Store（使用 Immer 中间件）
export const useAppStore = create<AppState>()(
  immer((set) => ({
    // 初始状态
    conversations: {},
    agents: {},
    messages: {},
    artifacts: {},
    messageIdsByConv: {},
    activeConversationId: null,
    previewArtifactId: null,
    pendingWritesByConv: {},
    
    // 核心 Action：应用 SSE 事件
    applyEvent: (event: StreamEvent) => {
      set((state) => {
        switch (event.type) {
          case 'part.delta': {
            // 增量追加文本
            const msg = state.messages[event.messageId]
            if (msg) {
              const part = msg.parts[event.partIndex]
              if (part && part.type === 'text') {
                part.content += event.delta.text  // ← Immer 允许直接修改！
              }
            }
            break
          }
          
          case 'message.added': {
            // 新消息加入
            const msg = event.message
            state.messages[msg.id] = msg
            state.messageIdsByConv[msg.conversationId]?.push(msg.id)
            break
          }
          
          case 'artifact.create': {
            // 新产物
            state.artifacts[event.artifact.id] = event.artifact
            break
          }
          
          // ... 更多事件类型
        }
      })
    },
    
    // 其他 Actions...
    setActiveConversation: (id) => {
      set((state) => { state.activeConversationId = id })
    },
  }))
)
```

### Immer 的作用（重要！）

Immer 让你可以**直接修改**状态（实际是不可变的）：

```typescript
// ❌ 没有 Immer 的写法（繁琐）
set((state) => ({
  ...state,
  messages: {
    ...state.messages,
    [msgId]: {
      ...state.messages[msgId],
      parts: state.messages[msgId].parts.map((p, i) =>
        i === partIndex ? { ...p, content: p.content + delta } : p
      )
    }
  }
}))

// ✅ 有 Immer 的写法（简洁）
set((state) => {
  state.messages[msgId].parts[partIndex].content += delta
})
```

### Normalized 状态（重要！）

项目使用 **normalized 存储**（按 ID 索引），不是嵌套数组：

```typescript
// ❌ 嵌套存储（不好）
conversations: [
  { id: 'conv_1', messages: [{ id: 'msg_1', ... }, ...] },
  ...
]

// ✅ Normalized 存储（好）
conversations: { 'conv_1': { id: 'conv_1', title: '...' } }
messages: { 'msg_1': { id: 'msg_1', conversationId: 'conv_1', ... } }
messageIdsByConv: { 'conv_1': ['msg_1', 'msg_2'] }
```

好处：
- 更新消息不需要找会话
- SSE 事件直接按 ID 更新
- 避免深层嵌套

---

## 9. SSE (Server-Sent Events)：实时通信

> **为什么重要**：AgentHub 的实时通信全靠 SSE，理解它才能理解事件推送机制。

### SSE 核心概念

SSE（Server-Sent Events）是浏览器原生 API，特点：
- **单向通信**：服务端 → 客户端（不像 WebSocket 双向）
- **自动重连**：浏览器自动处理断线重连
- **简单**：基于 HTTP，不需要 WebSocket 协议升级

### 客户端代码（实际代码）

```typescript
// src/components/stream-provider.tsx（完整代码）
'use client'

import { useEffect } from 'react'
import type { StreamEvent } from '@/shared/types'
import { API_BASE_URL } from '@/lib/config'
import { useAppStore } from '@/stores/app-store'

// 模块级变量防止 React StrictMode 双 mount 问题
let activeSource: EventSource | null = null
let refCount = 0

export function StreamProvider({ children }: { children: React.ReactNode }) {
  const applyEvent = useAppStore((s) => s.applyEvent)
  const setStreamConnected = useAppStore((s) => s.setStreamConnected)

  useEffect(() => {
    refCount++

    if (!activeSource) {
      // 1. 创建 SSE 连接
      activeSource = new EventSource(`${API_BASE_URL}/api/stream`)

      // 2. 连接成功
      activeSource.onopen = () => {
        setStreamConnected(true)
      }

      // 3. 连接错误（会自动重连）
      activeSource.onerror = () => {
        setStreamConnected(false)
      }

      // 4. 收到消息
      activeSource.onmessage = (e) => {
        const parsed = JSON.parse(e.data) as StreamEvent
        
        // 特殊处理连接确认
        if (parsed.type === 'connected') {
          setStreamConnected(true)
          return
        }

        // 应用事件到 store
        applyEvent(parsed)
      }
    }

    // 清理
    return () => {
      refCount--
      if (refCount <= 0) {
        activeSource?.close()
        activeSource = null
        refCount = 0
      }
    }
  }, [applyEvent, setStreamConnected])

  return <>{children}</>
}
```

### 服务端代码（Python）

```python
# backend/app/api/stream.py（简化示例）
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

@router.get("/stream")
async def stream_events():
    """全局 SSE 端点"""
    
    async def event_generator():
        # 订阅 EventBus
        queue = event_bus.subscribe()
        
        try:
            # 发送连接确认
            yield {"data": json.dumps({"type": "connected"})}
            
            # 持续推送事件
            while True:
                event = await queue.get()
                yield {"data": event.model_dump_json(by_alias=True)}
        finally:
            event_bus.unsubscribe(queue)
    
    return EventSourceResponse(event_generator())
```

### SSE 数据格式

```
data: {"type":"part.delta","conversationId":"conv_001","messageId":"msg_001","partIndex":0,"delta":{"type":"text.append","text":"好的"}}

data: {"type":"run.end","conversationId":"conv_001","runId":"run_001","status":"complete"}

data: {"type":"heartbeat"}
```

**注意**：
- 每个事件都是 `data: {...}\n\n` 格式
- 不使用 `event:` 字段（统一用 `data:`）
- 心跳间隔 15 秒，防止断连

---

## 10. Tailwind CSS + shadcn/ui：样式与组件

> **为什么低优先级**：可以在读代码时现学，不需要提前掌握。

### Tailwind CSS 核心概念

Tailwind 是原子化 CSS 框架，用 class 名直接写样式：

```tsx
// ❌ 传统 CSS
<div className="card">
  <style>{`.card { padding: 1rem; border-radius: 0.5rem; background: white; }`}</style>
</div>

// ✅ Tailwind
<div className="p-4 rounded-lg bg-white">
</div>
```

### 常用 Tailwind 类名

| 类别 | 示例 | 说明 |
|------|------|------|
| **间距** | `p-4`, `m-2`, `gap-3` | padding/margin/gap |
| **布局** | `flex`, `grid`, `items-center` | flexbox/grid |
| **尺寸** | `w-full`, `h-screen`, `max-w-lg` | width/height |
| **颜色** | `text-gray-500`, `bg-blue-100` | text/background |
| **圆角** | `rounded-lg`, `rounded-full` | border-radius |
| **响应式** | `md:flex`, `lg:w-1/2` | 媒体查询 |
| **暗色模式** | `dark:bg-gray-800` | 暗色主题 |

### shadcn/ui 组件

shadcn/ui 是「复制组件到项目」模式，不是 npm 包：

```
src/components/ui/
├── button.tsx      # 按钮
├── dialog.tsx      # 对话框
├── dropdown-menu.tsx
├── input.tsx
├── popover.tsx
├── scroll-area.tsx
├── separator.tsx
├── sheet.tsx
├── tabs.tsx
├── textarea.tsx
├── toast.tsx
├── tooltip.tsx
└── ...
```

使用方式：

```tsx
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader } from '@/components/ui/dialog'

<Button variant="default" size="sm">点击</Button>

<Dialog open={open} onOpenChange={setOpen}>
  <DialogContent>
    <DialogHeader>标题</DialogHeader>
    {/* 内容 */}
  </DialogContent>
</Dialog>
```

---

## 11. 技术映射对照表

如果你有 JavaScript/TypeScript 背景，这个对照表可以帮助你快速理解 Python 版本：

| TypeScript/JavaScript | Python | 项目用法 |
|----------------------|--------|---------|
| `express` / `koa` | `FastAPI` | Web 框架 |
| `Prisma` / `TypeORM` | `SQLAlchemy` | ORM |
| `Zod` | `Pydantic` | 数据验证 |
| `AsyncIterable` | `async generator` | 异步迭代器 |
| `AbortSignal` | `asyncio.Event` | 中止信号 |
| `EventEmitter` | `asyncio.Queue` | 事件发布/订阅 |
| `Promise.all()` | `asyncio.gather()` | 并发执行 |
| `Date.now()` | `int(time.time() * 1000)` | 时间戳 |
| `nanoid()` | `nanoid.generate()` | ID 生成 |
| `fetch()` | `httpx` | HTTP 客户端 |
| `dotenv` | `pydantic-settings` | 环境变量 |

---

## 12. 自检清单

完成阶段二学习后，你应该能回答以下问题：

### FastAPI

- [ ] FastAPI 应用是如何创建的？`lifespan` 生命周期管理器的作用是什么？
- [ ] `@router.get()` 和 `@router.post()` 装饰器的作用是什么？
- [ ] `Depends(get_db_session)` 依赖注入是怎么工作的？
- [ ] 启动后端后，`/docs` 页面能看到什么？

### SQLAlchemy

- [ ] 如何定义一个 SQLAlchemy 模型？`Mapped[]` 和 `mapped_column()` 的作用是什么？
- [ ] `ForeignKey("conversations.id", ondelete="CASCADE")` 是什么意思？
- [ ] 为什么 SQLite 需要设置 `PRAGMA foreign_keys=ON`？
- [ ] `AsyncSession` 和同步 Session 有什么区别？

### asyncio

- [ ] `async def` 和普通 `def` 有什么区别？
- [ ] `async generator` 是什么？Adapter 的 `stream()` 方法为什么用它？
- [ ] `asyncio.gather()` 和 `asyncio.create_task()` 有什么区别？
- [ ] `asyncio.Event` 在项目中用来做什么？

### Pydantic

- [ ] Pydantic 的 `BaseModel` 和 SQLAlchemy 的 `Base` 有什么区别？
- [ ] `Field(alias="runId")` 的作用是什么？为什么要用别名？
- [ ] `populate_by_name=True` 是什么意思？
- [ ] `Literal["run.start"]` 类型是什么？

### Next.js / React

- [ ] `'use client'` 指令的作用是什么？什么时候需要加？
- [ ] `layout.tsx` 和 `page.tsx` 分别是什么？
- [ ] 为什么项目没有 `src/app/api/` 目录？

### Zustand + SSE

- [ ] Zustand 的 `create()` 函数是怎么创建 store 的？
- [ ] Immer 中间件的作用是什么？为什么需要它？
- [ ] Normalized 状态是什么意思？为什么要这样设计？
- [ ] SSE 的 `EventSource` API 是怎么工作的？
- [ ] `applyEvent()` 函数的作用是什么？

### 综合

- [ ] 描述从「Python 后端产生事件」到「React UI 更新」的完整技术链路
- [ ] 为什么项目使用 SSE 而不是 WebSocket？
- [ ] snake_case 和 camelCase 是如何在项目中协调的？

---

> **下一步**：如果以上问题大部分能回答，进入阶段三（后端核心自底向上阅读），开始真正阅读业务代码。
>
> **推荐阅读顺序**：
> 1. `backend/app/main.py`（FastAPI 入口）
> 2. `backend/app/config.py`（配置管理）
> 3. `backend/app/db/engine.py`（数据库引擎）
> 4. `backend/app/db/models.py`（数据模型）
> 5. `backend/app/schemas/events.py`（事件定义）
> 6. `src/stores/app-store.ts`（Zustand store）
> 7. `src/components/stream-provider.tsx`（SSE 客户端）
