# UI BrightToDo 品牌迁移开发任务规划

**项目**：BrightToDo
**阶段**：UI 品牌一致性补齐
**规划日期**：2026-05-28
**工作分支**：`chore/a814802615/ui-branding`

---

## 一、阶段背景

当前仓库来自 FreeToDo 开源项目，前端页面标题、应用头部、动态岛标题、桌面壳启动文案、打包配置与部分国际化文案仍直接展示 FreeToDo。根据课程项目要求，BrightToDo 应作为最终产品名称出现在常规 UI 中；FreeToDo 只应在“关于/贡献”类页面中作为开源底座来源说明出现。

本阶段是 Sprint 2 前的品牌一致性补齐，不实现 OCR、日程编排等业务能力，不改动生成 API 代码和内部环境变量名称，避免扩大风险。

## 二、目标与范围

### 目标

1. 常规用户可见 UI 中的产品名称统一为 BrightToDo。
2. 设置中的“关于”区域补充“基于 FreeToDo 开源项目二次开发”的来源说明。
3. Electron/Tauri 产品名、窗口标题和启动提示统一使用 BrightToDo，降低演示时的品牌割裂感。
4. 保持现有构建、类型检查和 Biome 检查通过。

### 范围内

- Next.js `metadata` 页面标题与描述。
- 主 Header、全屏 Header、动态岛 Header、通知/托盘/启动等待页等用户可见文案。
- `zh/en` 国际化消息中的应用标题、欢迎标题、聊天标题、关于页说明。
- Electron Builder 与 Tauri 配置中的 `productName`、窗口标题、用户可见提示。
- `package.json` 应用名称与脚本中只影响显示或打包品牌的字段。

### 范围外

- `frontend/lib/generated/**` 生成代码注释。
- `FREETODO_*` 环境变量名、锁名、临时文件标记等内部兼容标识。
- README、打包指南等非运行 UI 文档的大规模改写。
- 新 Logo 设计与图标资产替换，本阶段只更新 alt 文案和显示名称。

## 三、任务拆解

| 任务ID | 任务描述 | 验收证据 |
|---|---|---|
| T-BR-1 | 盘点前端用户可见 FreeToDo/Free Todo 文案 | 搜索结果可解释，范围边界明确 |
| T-BR-2 | 替换 Web 应用标题、Header、动态岛与欢迎文案为 BrightToDo | 相关组件与 i18n 文件不再展示旧品牌 |
| T-BR-3 | 更新 Electron/Tauri 用户可见产品名、窗口标题、托盘提示与启动提示 | 配置和桌面壳源码显示 BrightToDo |
| T-BR-4 | 在设置“关于”区域添加 FreeToDo 来源说明 | 关于页保留 FreeToDo 来源信息 |
| T-BR-5 | 运行前端类型检查、Biome 检查，并执行品牌残留搜索 | `pnpm type-check`、`pnpm check` 通过，残留项均为允许范围 |

## 四、验收标准

1. Header、页面标题、欢迎页、聊天标题、动态岛标题均显示 BrightToDo。
2. Electron/Tauri 窗口标题、产品名、托盘提示、启动提示不再显示 FreeToDo。
3. 设置“关于”区域明确说明 BrightToDo 基于 FreeToDo 开源项目二次开发。
4. 常规 UI 源码搜索中，除“关于/贡献来源说明”、内部兼容变量、生成代码注释、非 UI 文档外，不存在用户可见 FreeToDo/Free Todo。
5. 独立审查 agent 和独立测试 agent 均确认无 P0/P1 后再提交。

## 五、风险与处理

| 风险 | 处理 |
|---|---|
| 误改内部 `FREETODO_*` 变量导致打包脚本失效 | 保留内部兼容变量，只改用户可见文案与产品名 |
| 生成代码中仍有 FreeTodo 注释导致搜索噪声 | 明确排除 `frontend/lib/generated/**`，不改生成文件 |
| 图标资产仍位于 `free-todo-logos` 路径 | 本阶段不设计新图标，只更新 alt 文案；后续可单独做图标资产迁移 |
