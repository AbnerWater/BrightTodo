# ScheduleSuggest 智能日程编排开发任务规划

## 阶段目标

本阶段聚焦 Sprint 2 的 US-009：实现 `POST /api/agent/schedule-suggest` 后端接口，基于待办优先级、截止时间、预估时长和课程约束，输出不与课程冲突的执行时段建议。

该阶段不实现 OCR 图片识别与前端日程确认 UI，只交付可测试、可联调的后端编排能力，为后续 OCR 结果确认和一键落地流程提供稳定接口。

## 输入依据

- `docs/04_接口契约/接口契约_Sprint2.md` 中的智能日程编排接口契约。
- `docs/03_冲刺计划/BrightToDo_迭代2冲刺目标.md` 中的 US-009、AC-S2-05。
- 已集成基线中的 Sprint 1 Agent 路由与 schema 风格。

## 交付范围

1. 后端 schema
   - 增加待编排待办、课程约束、建议时段、备选时段和响应模型。
   - 保持字段命名与 Sprint 2 契约一致。

2. 编排服务
   - 支持 `planning_start`、`planning_end`、`daily_available_hours`。
   - 默认使用北京时间作为本地时区。
   - 本阶段确定性规则暂定每日可安排窗口为 08:00-22:00，后续如需要夜间或自定义作息，可在请求契约中扩展起止时间字段。
   - 默认任务时长为 1 小时。
   - 高优先级、截止时间更早的任务优先安排。
   - 避开课程约束与已安排任务时段。
   - 返回最多 2 个备选时段。
   - 部分任务无法安排时返回 `unscheduled_todos`。
   - 全部任务无法安排时返回 `NO_AVAILABLE_SLOTS`。

3. Agent 路由
   - 增加 `POST /api/agent/schedule-suggest`。
   - 空待办或字段格式错误返回 `INVALID_INPUT`。
   - 无可用时段返回 `NO_AVAILABLE_SLOTS`。

4. 自动化测试
   - 覆盖课程冲突规避。
   - 覆盖高优先级优先编排。
   - 覆盖部分无法安排。
   - 覆盖路由响应字段与错误码。

## 不在本阶段范围

- `POST /api/agent/ocr-schedule` 和 `POST /api/agent/ocr-notes`。
- 前端编排建议时间轴和一键确认写入 UI。
- 外部 LLM 调用；本阶段采用确定性规则，保证课程演示和测试稳定。

## 验收标准

- `uv run ruff check .` 通过。
- `uv run pytest` 通过。
- `/api/agent/schedule-suggest` 能返回符合契约的 `suggestions`、`unscheduled_todos` 和 `planning_coverage_pct`。
- 建议时段不与课程约束重叠。
- 高优先级任务在同等条件下早于低优先级任务安排。
- 阶段完成后由独立审查 agent 和独立测试 agent 分别确认通过后再提交。
