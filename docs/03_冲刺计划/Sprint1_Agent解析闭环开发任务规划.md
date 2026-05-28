# Sprint 1 Agent 解析闭环开发任务规划

**项目**：BrightToDo
**阶段**：Sprint 1 补齐与闭环验收
**规划日期**：2026-05-28
**工作分支**：`feat/a814802615/sprint-1-agent`

---

## 一、阶段判定

根据 `docs/README.md`、`docs/01_立项与规划/BrightToDo_开发计划表.md`、
`docs/03_冲刺计划/BrightToDo_迭代1冲刺目标.md` 与
`docs/04_接口契约/接口契约_Sprint1.md`，Sprint 2 的前置条件是：

- Sprint 1 代码已合并主干；
- `/api/agent/parse-task` 接口稳定可用；
- 自然语言输入到解析确认再到待办创建的第一条 Agent 闭环可演示。

当前代码扫描结果显示，仓库已经具备 FreeToDo 的待办、日历、聊天、OCR 基础模块，
但尚未注册独立的 `/api/agent/parse-task` 自研接口。因此本阶段优先补齐 Sprint 1
自然语言解析闭环，再进入 Sprint 2 的 OCR 与日程编排开发。

---

## 二、阶段目标

交付“自然语言输入 -> 结构化解析 -> 用户确认修改 -> 创建待办”的可演示闭环，满足
Sprint 1 文档中的 US-007、US-008、US-012 与接口契约要求。

---

## 三、开发范围

### 3.1 后端范围

| 任务ID | 任务内容 | 主要文件 | 验收要点 |
|---|---|---|---|
| S1-BE-01 | 新增 Agent API Schema | `lifetrace/schemas/agent.py` | 请求和响应字段与 Sprint 1 接口契约一致 |
| S1-BE-02 | 新增 Agent 路由 | `lifetrace/routers/agent.py` | 提供 `POST /api/agent/parse-task` |
| S1-BE-03 | 注册 Agent 模块 | `lifetrace/core/module_registry.py` | 服务启动后接口可访问 |
| S1-BE-04 | 实现中文自然语言解析服务 | `lifetrace/services/agent_parse_service.py` | 支持标题、优先级、截止时间、预估时长、置信度 |
| S1-BE-05 | 解析异常规范化 | `lifetrace/routers/agent.py` | 空文本和超长文本返回 `INVALID_INPUT`，不暴露 500 裸错误 |

### 3.2 前端范围

| 任务ID | 任务内容 | 主要文件 | 验收要点 |
|---|---|---|---|
| S1-FE-01 | 新增自然语言输入入口 | `frontend/apps/todo-list/TodoToolbar.tsx`、`frontend/apps/todo-list/TodoList.tsx` | 待办页可打开 Agent 输入面板 |
| S1-FE-02 | 实现解析确认组件 | `frontend/apps/todo-list/NaturalLanguageTodoModal.tsx` | 字段可编辑，低置信度有提示 |
| S1-FE-03 | 确认创建待办 | `frontend/apps/todo-list/NaturalLanguageTodoModal.tsx` | 确认后调用现有待办创建接口 |
| S1-FE-04 | 类型映射 | `frontend/lib/types/index.ts` 或局部类型 | 字段与后端响应一致，避免破坏生成代码 |

### 3.3 测试范围

| 任务ID | 任务内容 | 主要文件 | 验收要点 |
|---|---|---|---|
| S1-TEST-01 | 后端解析服务单元测试 | `tests/test_agent_parse_service.py` | 覆盖至少 20 条 NL 测试用例核心断言 |
| S1-TEST-02 | 后端接口测试 | `tests/test_agent_router.py` | 覆盖正常解析、空文本、超长文本 |
| S1-TEST-03 | 质量检查 | 命令行 | `uv run ruff check .`、相关 pytest 通过 |
| S1-TEST-04 | 前端静态检查 | 命令行 | `pnpm type-check` 与可执行的 Biome 检查通过或记录阻塞 |

---

## 四、实现策略

1. 后端先实现确定性解析兜底，不依赖外部 LLM 可用性，保证课程演示和测试稳定。
2. 中文时间解析优先覆盖 Sprint 1 测试计划列出的表达：今天、明天、后天、三天后、
   一周后、下周一、下下周三、本周内、具体月日、今晚、上午、下午、中午。
3. 预估时长解析使用规则方式处理“半小时、90分钟、两个小时、4小时”等常见表达。
4. 前端使用手写局部 API 调用，避免重新生成整套 OpenAPI 客户端造成大面积噪声。
5. 文档、注释和用户可见新增文本保持中文。

---

## 五、验收标准

| 编号 | 验收标准 | 验证方式 |
|---|---|---|
| AC-S1-01 | `POST /api/agent/parse-task` 接受中文自然语言并返回结构化 JSON | pytest 接口测试 |
| AC-S1-02 | 返回字段包含 `task_title`、`priority`、`due`、`duration`、`description`、`confidence`、`raw_text`、`parse_version` | pytest 接口测试 |
| AC-S1-03 | 20 条 NL/时间解析用例中核心时间、优先级、时长解析准确率达到文档要求 | pytest 单元测试 |
| AC-S1-04 | 空文本和超过 500 字符文本返回 400 与 `INVALID_INPUT` | pytest 接口测试 |
| AC-S1-05 | 前端可输入自然语言，展示可编辑解析结果，确认后创建待办 | 手动或浏览器验证 |
| AC-S1-06 | 新增代码通过 Ruff、pytest 与前端类型检查 | 命令行验证 |

---

## 六、审查与测试 Gate

本阶段开发完成后，提交前必须完成以下流程：

1. 创建独立审查 agent，要求其从代码审查角度检查行为缺陷、接口契约偏差和缺失测试。
2. 创建独立测试 agent，要求其从测试角度运行或复核后端与前端验证命令。
3. 主 agent 根据审查和测试反馈修复所有 P0/P1 问题。
4. 仅当审查和测试均无阻塞问题后，执行 git commit。

---

## 七、阶段外范围

以下任务保留到 Sprint 2：

- `/api/agent/ocr-schedule` 课表 OCR 识别；
- `/api/agent/ocr-notes` 手稿/笔记 OCR 识别；
- `/api/agent/schedule-suggest` 智能日程编排；
- OCR 结果确认与完整图片到日程的闭环演示。
