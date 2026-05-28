# UI 上传与运行稳定修复开发任务规划

**项目**：BrightToDo
**阶段**：前端运行问题修复与文件导入待办闭环
**规划日期**：2026-05-29
**工作分支**：`fix/a814802615/ui-upload-stability`

---

## 一、阶段背景

当前运行实例暴露出三个直接影响课程演示的问题：常规 UI 仍出现 FreeToDo 文案、待办面板在后端未连通时显示泛化的 `API Error:500`、AI 聊天输入区缺少图片和文件上传入口。与此同时，前序 Sprint 1 Agent 解析、UI 品牌迁移和智能日程编排提交尚未进入当前主线运行实例，因此本阶段先集成这些已完成成果，再补齐“用户文件导入后自动解析待办”的闭环能力。

## 二、阶段目标

1. 常规运行 UI 中产品名统一为 BrightToDo，仅“关于/来源说明”保留 FreeToDo 开源底座信息。
2. 后端正常启动时 `/api/todos` 返回 200；后端未连接时，待办面板给出可行动的中文提示，而不是裸露 `API Error:500`。
3. AI 聊天输入区提供文件上传入口，支持图片、文本、PDF、DOCX 文件解析为待确认任务。
4. 上传解析默认不自动落库，用户确认后再批量创建草稿待办。
5. 完成后通过独立审查 agent 和独立测试 agent 的提交前 Gate。

## 三、开发范围

### 3.1 集成范围

| 任务ID | 任务内容 | 验收要点 |
|---|---|---|
| FIX-INT-01 | 在新工作树中基于当前主线创建修复分支 | 分支为 `fix/a814802615/ui-upload-stability` |
| FIX-INT-02 | cherry-pick Sprint 1 Agent 解析提交 | `/api/agent/parse-task` 可用 |
| FIX-INT-03 | cherry-pick UI 品牌迁移提交 | 常规 UI 不再显示旧品牌 |
| FIX-INT-04 | cherry-pick 智能日程编排提交 | `/api/agent/schedule-suggest` 可用 |

### 3.2 后端范围

| 任务ID | 任务内容 | 主要文件 | 验收要点 |
|---|---|---|---|
| FIX-BE-01 | 新增导入待办响应模型 | `lifetrace/schemas/agent.py` | 返回文件结果、解析任务、已创建待办、预览文本和耗时 |
| FIX-BE-02 | 新增文件解析服务 | `lifetrace/services/agent_import_service.py` | 支持图片、TXT/MD/CSV/JSON、PDF、DOCX |
| FIX-BE-03 | 新增 multipart 接口 | `lifetrace/routers/agent.py` | `POST /api/agent/import-todos` 支持 `files[]`、`reference_time`、`create_todos` |
| FIX-BE-04 | 文件大小和类型校验 | 解析服务与接口测试 | 单文件 10MB、最多 5 个文件，非法类型返回 `INVALID_FILE_TYPE` |
| FIX-BE-05 | 可选创建草稿待办 | 解析服务 | `create_todos=true` 时创建草稿待办并返回 ID |

### 3.3 前端范围

| 任务ID | 任务内容 | 主要文件 | 验收要点 |
|---|---|---|---|
| FIX-FE-01 | 聊天输入区新增上传按钮 | `InputBox.tsx`、`ChatInputSection.tsx` | Paperclip 入口可见且支持多文件选择 |
| FIX-FE-02 | 展示文件列表与上传状态 | `ChatInputSection.tsx` | 图片缩略图、文档文件名/类型/大小、移除按钮、失败提示 |
| FIX-FE-03 | 展示待确认任务列表 | `ChatInputSection.tsx` | 用户可编辑标题、时间、优先级并删除条目 |
| FIX-FE-04 | 确认后批量创建草稿待办 | `ChatInputSection.tsx` | 调用现有 `/api/todos` 创建并刷新待办列表 |
| FIX-FE-05 | 改善待办加载错误提示 | `TodoList.tsx`、国际化文案 | 后端未连接时提示重新启动服务 |

## 四、验收标准

1. `scripts/start_dev.ps1 -SkipInstall` 启动后，浏览器打开 BrightToDo 运行页面。
2. 主界面、聊天欢迎区、待办面板等常规 UI 不再出现 FreeToDo/Free Todo。
3. 后端可用时 `/api/todos` 返回 200；后端不可用时待办面板显示“后端服务未连接”类提示。
4. 聊天输入框内有上传入口，能选择并展示图片、文本、PDF、DOCX 文件。
5. 上传解析返回待确认任务，用户可编辑、删除并确认创建草稿待办。
6. `uv run ruff check .`、`uv run pytest`、`pnpm check`、`pnpm type-check` 通过或记录明确阻塞。
7. 独立审查 agent 与独立测试 agent 均确认无 P0/P1 阻塞后再提交。

## 五、风险与处理

| 风险 | 处理 |
|---|---|
| 图片解析依赖 LLM 配置，测试环境可能不可用 | 图片路径复用现有视觉提取能力，测试中通过替身覆盖；未配置时返回可解释失败结果 |
| PDF/DOCX 新依赖引入锁文件变更 | 在 `pyproject.toml` 中声明依赖并更新锁文件，检查安装与测试结果 |
| 文件解析误判普通文本为待办 | 默认展示待确认任务，不自动落库；用户确认后才创建草稿 |
| 后端未启动导致前端错误信息误导 | 待办面板识别连接类错误并给出启动命令提示 |
| 上传确认 UI 过重影响聊天输入可用性 | 将确认列表放在输入区上方，保持按钮尺寸稳定并可清空 |

## 六、审查与测试 Gate

开发完成后，提交前执行以下流程：

1. 创建独立审查 agent，从接口契约、文件解析边界、前端交互和品牌残留角度审查。
2. 创建独立测试 agent，从后端单元/接口测试、前端静态检查和浏览器验收角度测试。
3. 主 agent 修复所有 P0/P1 问题，并对可接受残余风险记录说明。
4. 审查与测试均 PASS 后再执行提交。
