# min-codingAgent

一个**最小实现的命令行编码 Agent**：把用户的自然语言指令交给 LLM，由 LLM 自主决定调用哪些本地工具（读写文件、执行命令、检索本地知识库），执行结果回灌给模型，循环往复直到任务完成。

没有框架、没有 LangChain、没有抽象层 —— 整个主循环不到 60 行，方便逐行读懂一个 coding agent 到底是怎么跑起来的。

---

## 目录

- [它是什么](#它是什么)
- [运行原理](#运行原理)
- [目录结构](#目录结构)
- [环境准备](#环境准备)
- [配置 .env](#配置-env)
- [快速开始](#快速开始)
- [内置工具](#内置工具)
- [本地知识库（RAG）](#本地知识库rag)
- [如何新增一个工具](#如何新增一个工具)
- [开发与自测](#开发与自测)
- [已知限制与待办](#已知限制与待办)

---

## 它是什么

- **入口**：`agent_loop.py`，一个 REPL —— 你输入一句话，Agent 自己干活，干完再把话回给你。
- **模型**：任何 OpenAI 兼容接口（当前配置走 DeepSeek），支持流式输出和 `tool_calls`。
- **工具**：8 个，全部是本地实现，定义在 `tools/` 包里。

| 能力 | 工具 |
| --- | --- |
| 看 | `read`、`glob` |
| 改 | `write`（新建）、`edit`（精确替换） |
| 跑 | `bash`（**执行前需人工确认**） |
| 查 | `rag_add`、`rag_query`、`rag_list`（本地向量库） |

典型用途：让 Agent 读你项目里的文件、按你的描述改代码、跑命令验证结果、并能在你自己的语料（PDF/DOCX/笔记）里做语义检索。

## 运行原理

```
        用户输入
           │
           ▼
   ┌───────────────────┐
   │  chat.completions │◄──────────────┐
   │   stream=True     │               │
   └─────────┬─────────┘               │
             │ 流式吐出 content / tool_calls
             ▼                         │
     有 tool_calls ? ──否──► 打印回答，回到等待输入
             │是                       │
             ▼                         │
   p_which_tool_use() 人工确认(bash)     │
             ▼                         │
   model_validate(arguments) 参数校验    │
             ▼                         │
      tool.execute(params, ctx)        │
             ▼                         │
   把结果以 role="tool" 追加进 messages ──┘
```

三个关键点：

1. **工具声明由 Pydantic 自动生成**。`Tool.declaration()` 调 `model_json_schema()` 把参数模型转成 JSON Schema 喂给模型，所以加一个字段只需要改一个 `BaseModel`（见 `tools/tools_class.py:17`）。
2. **模型返回的参数一定不可信**，`tools/tools.py:37` 统一用 `model_validate` 兜住，再进 `execute`；任何异常都被 `tools_calls` 捕获成一段文本回给模型，而不是让整个进程崩掉。
3. **工具执行结果不是打印而是回灌**。每个工具返回的字符串会作为 `role="tool"` 消息进入 `messages`，模型据此决定下一步 —— 这就是 Agent 能连续行动的机制。

## 目录结构

```
min-codingAgent/
├── agent_loop.py          # 入口：REPL + 主循环（流式解析 + tool_calls 归并）
├── get_client.py          # 从 .env 构造 OpenAI 客户端
├── requirements.txt       # 依赖（已钉住关键版本）
├── .env                   # 密钥配置（已在 .gitignore 中，不会进仓库）
├── tools/                 # 工具包
│   ├── __init__.py
│   ├── tools_class.py     # Tool / ToolContext 基类、路径解析
│   ├── tools.py           # TOOL_TABLE 注册表 + 分发 + bash 人工确认
│   ├── read_tools.py      # read
│   ├── write_tools.py     # write
│   ├── edit_tool.py       # edit
│   ├── bash_tool.py       # bash
│   ├── glob_tool.py       # glob
│   └── rag_tools.py       # rag_add / rag_query / rag_list（chromadb）
├── chroma-data/           # 向量库持久化目录（已 gitignore）
├── data/                  # 语料：docx / odt（已 gitignore）
└── test_data/             # 语料：pdf + markdown 笔记（已 gitignore）
```

> `tools/` 内部一律使用**相对导入**（`from .tools_class import ...`），因此：
> - 必须在**项目根目录**启动：`python agent_loop.py`
> - 单独调试某个工具模块时必须用模块方式：`python -m tools.bash_tool`，直接 `python tools/bash_tool.py` 会报 `attempted relative import with no known parent package`。

## 环境准备

要求 **Python ≥ 3.10**（代码用到 `int | None`、`list[str]` 等写法）。

```bash
conda create -n min_agent python=3.12 -y
conda activate min_agent
pip install -r requirements.txt
```

或使用 venv：

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

依赖里有两个需要留意的：

- `chromadb==1.5.9` —— **不要随意升级**。`rag_tools._reset_cache()` 依赖其私有 API `SharedSystemClient.clear_system_cache()` 来避免读到陈旧的向量库状态（多进程/删库重建场景），换版本后该 API 可能消失，届时只会打印一条警告并退化为"可能读到陈旧数据"。
- `openai==3.19.0`、`pydantic==2.13.5` —— 前者决定 `tool_calls` 的流式增量结构，后者决定工具参数 Schema 的生成，都属于升级需回归的组件。

## 配置 .env

在项目根目录创建 `.env`（`get_client.py` 与 `rag_tools.py` 都会 `load_dotenv()`）：

```ini
# 对话模型（OpenAI 兼容接口）
base_url=https://api.deepseek.com
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
Model=deepseek-chat

# 向量化服务（rag_* 工具用，需兼容 OpenAI embeddings 接口）
EMBEDDING_KEY=sk-xxxxxxxxxxxxxxxx
EMBEDDING_URL=https://api.siliconflow.cn/v1
```

| 变量 | 用途 |
| --- | --- |
| `base_url` | 对话接口的 base_url，`get_client.py:8` 读取 |
| `DEEPSEEK_API_KEY` | 对话接口的 API Key |
| `Model` | 模型名，`agent_loop.py:16` 读取（变量名首字母大写，注意别写错） |
| `EMBEDDING_KEY` | 向量化服务的 API Key |
| `EMBEDDING_URL` | 向量化服务的 base_url |

> `EMBEDDING_KEY` 这个**变量名本身**也很重要：`rag_tools.py:50` 是通过 `api_key_env_var="EMBEDDING_KEY"` 让 chromadb 自己去读这个环境变量的。直接把 key 值传给 chromadb 会导致它无法持久化配置，别的进程打开同一个 collection 时会静默回退到内置 ONNX 模型（384 维），**检索结果全错且不报错**。

## 快速开始

```bash
cd min-codingAgent
conda activate min_agent
python agent_loop.py
```

启动后直接说人话，例如：

```
--------------------------------------------
帮我看看 tools/tools.py 里注册了哪些工具
--------------------------------------------

Tool Use:  read
----------------------
（Agent 读文件、组织答案、流式打印）
```

- 输入 `exit` 或 `q` 退出；`Ctrl-D` / `Ctrl-C` 也会安全退出。
- **`bash` 工具每次执行前都会拦下来问你**，输入 `y`/回车放行，`no`/`n`/`q`/`exit` 拒绝（拒绝信息会回给模型，让它换个做法）。

## 内置工具

所有工具的参数都由模型自行填写，下表列出各自的能力边界与安全约束。

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `read` | `path`、`offset=1`、`limit` | 读文本文件。默认最多 2000 行 / 200KB，超出会截断并在末尾提示续读的 `offset`；成功读取的文件会记入 `ctx.readed_file` 白名单 |
| `glob` | `pattern`、`path="."`、`count` | 按 glob 通配符定位文件（支持 `**`），只返回文件、不返回目录，结果按路径排序、最多显示 `count` 个 |
| `write` | `path`、`text=""` | **只用于新建文件**；目标已存在则直接拒绝（防止模型误覆盖），父目录会自动创建 |
| `edit` | `path`、`old_str`、`new_str` | 精确字符串替换。要求文件**已在本会话被 read 过**，且 `old_str` 在文件中**恰好出现一次**（0 次或多处都会拒绝并要求模型重新读取），替换后写回 |
| `bash` | `command`、`timeout` | 在 `ctx.cwd` 下执行 `bash -c <command>`，返回 `CompletedProcess` 的字符串表示。含 `rm -rf /` 的指令直接拒绝；**执行前需用户确认** |
| `rag_add` | `documents`、`col_name` | 文本片段入库（upsert，同 id 覆盖），返回入库数量与该库当前总数 |
| `rag_query` | `query`、`col_name`、`k=4` | 语义检索，返回片段 + 出处 + `dist`（越小越相关），每条正文截断 1200 字符；库名不存在时会列出所有可用库名 |
| `rag_list` | — | 列出所有向量库及片段数量，用于确认"库名到底叫什么" |

**路径解析**：所有文件类工具都走 `get_Right_path()`（`tools/tools_class.py:32`），相对路径基于 `ctx.cwd`（即启动目录）解析为绝对路径，也接受绝对路径。

**两层安全设计**：

1. `write` 拒绝覆盖 + `edit` 要求先 `read` —— 前者防手滑新建，后者保证模型改的是它真正看过的内容（而不是凭记忆瞎改）。
2. `bash` 人工确认 —— 唯一能造成不可逆副作用的工具，所以每次执行前都必须由人点头。

## 本地知识库（RAG）

三个 `rag_*` 工具基于 **chromadb + BAAI/bge-m3**（走 OpenAI 兼容的 embeddings 接口），向量库持久化在 `rag_tools.py:10` 的 `DB_DIR`。

**入库**时每个片段需要一段结构化元数据：

```python
Metadata(
    docs_name="离散数学笔记",        # 文档名
    docs_path="note/relations.md",  # 文档路径（检索结果里作为出处显示）
    source_type="md",               # 只能是 md / txt / pdf / docx / odt
)
```

- 元数据模型开了 `extra="forbid"`：多传字段直接报错，而不是被静默丢掉。
- `ids` / `docs` / `meta` 三个列表长度必须一致，否则在 `Documents` 校验阶段就报错。

**推荐用法**：先 `rag_list` 确认库名 → 再 `rag_add` 入库 → 再 `rag_query` 检索。检索拿到的只是片段，需要完整上下文时让 Agent 用 `read` 去读 `docs_path` 指向的原文件。

**多进程注意事项**：`rag_tools` 在每个工具入口都会调一次 `_reset_cache()`，主动丢弃 chromadb 的进程内系统缓存后再干活。因为 chromadb 按路径缓存底层 `System`，别的进程删库/重建后，本进程即使重新 `PersistentClient` 也只会拿到陈旧状态（症状是 `rag_list` 报出已不存在的库、`rag_add` 报 `readonly database`）。这也是 `chromadb` 版本被钉死的原因。

**迁移项目位置时记得改** `rag_tools.py:10`：

```python
DB_DIR="/mnt/agent-exercise/min-codingAgent/chroma-data"   # 硬编码绝对路径
```

## 如何新增一个工具

四步，以加一个 `todo` 工具为例：

**1. 新建 `tools/todo_tool.py`**，一个参数模型 + 一个执行函数：

```python
from .tools_class import ToolContext, Tool, get_Right_path
from pydantic import BaseModel, Field

class TodoParams(BaseModel):
    path: str = Field(description="要写入清单的文件路径")

def _todo(p: TodoParams, ctx: ToolContext) -> str:
    p_path = get_Right_path(p.path, ctx)
    ...
    return "结果文本（会原样回灌给模型）"

todo_tool = Tool(
    name="todo",
    description="工具的用途说明 —— 这段文字直接决定模型何时会用它，写清楚「什么时候用、什么时候别用」",
    params=TodoParams,
    execute=_todo,
)
```

**2. 在 `tools/tools.py` 顶部导入并注册**：

```python
from .todo_tool import todo_tool

TOOL_TABLE = {
    ...,
    todo_tool.name: todo_tool,
}
```

**3. 补一个冒烟测试块**（可选但强烈建议）：

```python
if __name__ == "__main__":
    print(_todo(TodoParams(path="TODO.md"), ToolContext(cwd=".")))
```

**4. 验证**：

```bash
python -m tools.todo_tool                      # 单模块自测
python -c "import tools.tools as t; print(sorted(t.TOOL_TABLE))"   # 确认已注册
python agent_loop.py                           # 端到端试一次
```

约定：**`execute` 不要抛异常，尽量返回描述性的错误字符串**（比如 `"Wrong:...请先使用 read 工具阅读"`），模型看到就能自己纠正；抛异常虽然会被 `tools_calls` 兜住，但错误信息会变得难读。

## 开发与自测

```bash
# 必须在项目根目录执行
python -m tools.bash_tool        # bash 工具自测
python -m tools.glob_tool        # glob 工具自测
python -m tools.rag_tools        # RAG 冒烟测试（用临时库，结束自动清理）

# 确认工具注册表
python -c "import tools.tools as t; print(sorted(t.TOOL_TABLE))"

# 全项目语法检查
python -m compileall -q .
```

> RAG 冒烟测试会真实调用 embedding 接口（需要联网 + `EMBEDDING_*` 配置正确）。

## 已知限制与待办

**功能缺口**

- `tools/tools_class.py:29` `truncated_for_text()` 是空实现，尚未接入。
- `tools/tools.py:74` `check_readedFile()`（本意是用 `git diff --stat` 把已改动的文件移出 `readed_file` 白名单）目前无人调用，白名单只增不减。
- `bash` 之外的工具（`write` / `edit`）没有二次确认，模型的写操作会直接落盘。

**安全边界（当前是"玩具级"，谨慎用于真实仓库）**

- `dangerous_command` 只做 `"rm -rf /"` 的子串匹配，轻易可绕过；没有命令白名单/黑名单体系。
- 没有沙箱：`write` / `edit` 可以写到工作目录之外，`read` 也不限制目录穿越。
- `ctx.readed_file` 是唯一的写操作闸门，属于"防手滑"而非"防恶意"。

**健壮性**

- `messages` 无限增长，没有 token 统计与历史裁剪，长会话会撞上下文上限。
- 主循环没有最大轮次上限，模型陷入反复调用工具时会一直转下去。
- API 调用失败（网络/限流）没有重试与友好提示。
- 文件名风格不统一：`read_tools.py` / `write_tools.py` / `rag_tools.py`（复数）与 `edit_tool.py` / `bash_tool.py` / `glob_tool.py`（单数）混用，建议统一。

**环境相关**

- `rag_tools.py:10` 的 `DB_DIR` 是硬编码绝对路径，换机器/换目录必须改。
- `chromadb==1.5.9` 被 `_reset_cache()` 的私有 API 依赖钉住，升级前请先读该函数的注释。
