# BrightToDo

BrightToDo 是一个面向学生学习场景的智能任务管理系统，也是敏捷 Web 开发课程项目。项目基于 FreeTodo 开源项目的基础 Todo 框架进行二次开发，在已有待办管理、日历视图和桌面端能力之上，逐步集成 AI Agent 能力，降低学生从课程信息、手稿笔记和自然语言描述中整理任务的成本。

## 项目定位

传统 Todo 工具通常要求用户手动录入任务、截止时间和优先级。BrightToDo 的目标是在 FreeTodo 稳定底座上扩展 ToDo Agent，使系统能够从自然语言、课表截图和课堂笔记中提取任务信息，并结合课表约束给出可确认、可调整的日程建议。

课程项目开发重点分为两部分：

- 复用 FreeTodo 已有能力：待办 CRUD、父子任务、拖拽排序、日历视图、前后端基础架构。
- 自研 AI Agent 能力：自然语言任务解析、中文时间表达解析、OCR 识别、任务确认交互、智能日程编排。

## 核心功能规划

### 已复用基础能力

- 待办创建、编辑、删除和完成状态管理。
- 父子任务与任务完成进度展示。
- 列表拖拽排序与顺序持久化。
- 日历视图中的待办展示。
- Web 前端、FastAPI 后端和本地 SQLite 存储。

### 课程自研能力

- 自然语言解析：将中文任务描述解析为标题、优先级、截止时间和预估时长。
- 中文时间解析：支持“明天”“下周一”“三天后”等相对时间表达，并输出统一时间格式。
- 课表 OCR：从课表截图中识别课程名称、上课时间和地点，形成时间约束。
- 手稿 OCR：从课堂手稿或笔记图片中提取待办事项、截止日期和关联课程。
- 结果确认：将 AI 识别结果以可编辑表单展示，用户确认后创建待办。
- 日程编排：结合课表、截止日期、优先级和预估时长，生成可执行的任务安排建议。

## 技术栈

| 模块 | 技术 |
|---|---|
| 后端 | Python 3.12, FastAPI, SQLModel, SQLAlchemy |
| 数据存储 | SQLite, ChromaDB |
| AI 集成 | OpenAI API, DashScope, Agno Agent Framework |
| OCR 与图像处理 | RapidOCR, Pillow, OpenCV |
| 前端 | Next.js, React, TypeScript |
| UI 与交互 | Radix UI, Tailwind CSS, dnd-kit |
| 桌面端 | Electron, Tauri |
| 工程工具 | uv, pnpm, Ruff, Biome |

## 目录结构

```text
.
├── lifetrace/              # FastAPI 后端、服务层、数据访问、LLM 与 Agent 相关模块
├── lifetrace/config/       # 运行配置，config.yaml 由 default_config.yaml 生成
├── lifetrace/data/         # 运行期数据目录，本地数据库和向量库不应提交
├── free-todo-frontend/     # Next.js 前端、Electron/Tauri 桌面端封装和脚本
├── docs/                   # 课程项目文档、立项报告、冲刺计划和开发计划
├── tests/                  # 后端测试
└── scripts/                # 项目辅助脚本
```

## 本地开发

### 环境要求

- Python 3.12
- Node.js 与 pnpm
- uv

### 后端启动

在仓库根目录执行：

```bash
uv sync
python -m lifetrace.server
```

后端服务会从 `8001` 开始自动选择可用端口。

### 前端启动

进入前端目录后执行：

```bash
cd free-todo-frontend
pnpm install
pnpm dev
```

前端开发服务会通过脚本自动检测可用端口。

## 质量检查

后端：

```bash
uv run ruff check .
uv run ruff format .
```

前端：

```bash
cd free-todo-frontend
pnpm lint
pnpm format
pnpm check
pnpm type-check
```

## 迭代计划

项目周期为 2026-04-28 至 2026-06-23，采用两轮核心 Sprint 推进。

| 阶段 | 时间 | 目标 |
|---|---|---|
| Sprint 1 | 2026-05-12 至 2026-05-25 | 完成 FreeTodo 复用验证，并交付“自然语言输入 -> AI 解析 -> 用户确认 -> 创建待办”的端到端闭环 |
| Sprint 2 | 2026-05-26 至 2026-06-08 | 完成课表/手稿 OCR、识别结果确认、智能日程编排和 Agent 主入口集成 |
| 稳定化与答辩 | 2026-06-09 至 2026-06-23 | 回归测试、缺陷修复、文档整理、演示准备和课程答辩 |

## 文档

课程项目相关文档位于 `docs/`：

- `docs/项目立项报告_v2.md`
- `docs/BrightToDo_开发计划表.md`
- `docs/BrightToDo_迭代1冲刺目标.md`
- `docs/团队章程_v2.md`

## 开源基础与说明

本项目以 FreeTodo 开源项目作为基础 Todo 框架，并围绕课程目标进行 AI Agent 集成开发。开发过程中应清晰区分“开源底座复用功能”和“课程自研功能”，便于项目验收、代码评审和课程答辩。

运行期配置、数据库、日志和本地密钥不应提交到版本库。API Key 等敏感信息请通过本地配置文件或环境变量管理。
