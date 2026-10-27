# HomeMind Figma Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将用户已批准的 Figma 浅色科技控制台同步到现有 React，修正画稿中发现的开关/手机时钟布局问题，保持当前 M3 功能和账号边界。

**Architecture:** 使用既有 React、Ant Design、CSS Modules、TanStack Query。统一 CSS 语义变量和 Ant Design theme；沿用现有组件与 API，只调整视觉结构、设备/只读传感的展示层次和必要的表单布局。旧规则与会话实现不改。

**Tech Stack:** React 19、TypeScript、Vite、Ant Design、Vitest、Playwright。

用户已明确答复“按此方向同步，代码中修复排版”。Figma Starter MCP 额度已耗尽，不调用其他通道绕过，不把代码修正说成 Figma 已修正。在现有独立 HomeMind 仓库创建 `codex/figma-frontend-redesign` 分支继续，保留用户 README 的打开路径与已安装依赖；不另复制密钥或更换运行目录。

## Task 1：同步全部现有页面

**Files:**

- Modify: `frontend/src/index.css`、`frontend/src/App.tsx`、`frontend/src/App.module.css`、`frontend/src/components/ConnectionCard.tsx`。
- Modify: `frontend/src/components/simulation/SimulationDashboard.tsx`、`EntityCard.tsx`、`Simulation.module.css`；仅在布局需要时调整同目录配置表单与管理组件。
- Modify: `frontend/src/components/tasks/Tasks.module.css`、`TaskComposer.tsx`、`TasksPanel.tsx`、`TaskDetail.tsx`、`PreferencesPanel.tsx`。
- Modify: `frontend/src/components/auth/AuthForm.tsx`、`Auth.module.css`。

- [ ] 读取本地实际 Figma 导出图 `output/figma-desktop-overview.png`、`output/figma-desktop-tasks.png` 和 `output/figma-components.png`，并参照设计简报/节点映射。
- [ ] 定义统一主题变量并映射 Ant Design，准确使用画稿中的颜色、间距和字体回退：

```css
:root {
  --hm-canvas: #f5f7fb;
  --hm-surface: #fff;
  --hm-text: #172b4d;
  --hm-muted: #5e6c84;
  --hm-border: #dfe5ef;
  --hm-primary: #2563eb;
  --hm-primary-soft: #eff6ff;
  --hm-teal: #0f766e;
  --hm-teal-soft: #f0fdfa;
  --hm-warning: #92400e;
  --hm-danger: #b91c1c;
  font-family: Inter, "Noto Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif;
}
```

- [ ] 用浅色约 224px 侧栏、紧凑标题、蓝色选中导航取代深绿侧栏与大宣传标题；每个视图一个与当前页一致的 h1。移动端导航和退出保持可用。
- [ ] 家庭概览保留实际统计、读取状态与调试时钟，设备和传感器分组展示。所有房间/设备来自 API；传感器的模拟事件仍保留在明确标注的演示控制中。温度未知不能回填为 0，归档/离线/延迟语义不改。
- [ ] 卡片按类型显示正确图标，当前读回与待应用设置分开；保留开关、亮度、模式、温度、风速、开度以及明确的“应用设置”。控件列用 `minmax(0, 1fr)`、`min-width: 0`、开关 `flex-shrink: 0`，不沿用画稿 120px 开关挤入 95px 列的错误。
- [ ] 仿真时钟使用自动高度与换行，在手机宽度不产生重叠；读取/推进/重置仍可操作。非空房间删除保持禁用，危险操作保留确认。
- [ ] 任务页对齐画稿的模板选择、表单/历史双列和动作/目标分区；不新增自然语言功能、静态任务或伪造数据。保留幂等 submission 状态及跨标签会话保护。
- [ ] 偏好页为编辑/说明布局；登录注册为统一蓝灰视觉，桌面分栏、手机以表单为主。保留输入规则、pending 防重复、错误、数据库未就绪与重试状态。
- [ ] 自查 CSS 引用与长名称、空状态、未知/失败状态，无无意义的大面积空白或横向溢出。

不为纯视觉可逆调整新增逐样式断言；使用已有功能测试与真实浏览器核对。只有实际变更业务行为时才新增必要的失败/回归用例。

## Task 2：实际验证与修正

**Files:** `frontend/src/App.test.tsx`、`frontend/e2e/foundation.spec.ts` 等现有测试仅调整已改变的页面标题/画面证据文件名；`output/` 保存新日志、截图和临时验证配置，不覆盖 M3 原始截图。

- [ ] 基线 `npm.cmd test -- --run`，记录实际结果。
- [ ] 运行以下命令并保留输出，失败先查原因再修：

```powershell
npm.cmd test -- --run
npm.cmd run lint
npm.cmd run build
```

- [ ] 检查 5174/8100 是否为其他用户进程占用。不停止未知服务，不使用已有用户家庭测试；浏览器启动专属临时进程、连本项目独立测试库。必要时用忽略的临时 Playwright 配置指定其他可用端口和准确 Origin。
- [ ] 运行现有全部 Playwright 账号、设备、配置、偏好和任务检查。实际截图存 `output/figma-sync-*.png`，不覆盖 `m3-*.png`。
- [ ] 查看新截图：桌面概览/任务/配置/偏好/登录；390px 与 360px 关键页面，重点检查开关、时钟、长名称、按钮/表单无溢出。真实业务字段不改成 Figma 中的样例值。
- [ ] 必要修正后只重跑受影响检查；最终前端检查、规格和代码质量审阅通过后进入交付。

## Task 3：文档、审阅与交付

**Files:** `README.md`、`CURRENT_CONTEXT.md`、`docs/homemind-development-roadmap.md`、`docs/verification/figma-redesign.md`、`docs/superpowers/specs/2026-10-27-figma-redesign-brief.md`。

- [ ] 按本任务范围独立审阅规格，再审代码质量，修正发现的问题并复核。
- [ ] 更新设计批准状态、实际同步范围、检查结果和截图。Figma 稿仍有待修项，不能记成已与最终代码完全一致。
- [ ] 更新 README：启动方式不变，提供设计链接和已同步页面说明；记录本轮未运行真实模型，用户的密钥不进入文档或前端。
- [ ] 运行 `git diff --check`，确认仅本项目目标文件变化，保存到本地开发分支。不推送、不发布、不擅自推进 M4 实现。

本次同步完成后返回 M4 的已授权工作入口，先交付本次界面结果，不把 UI 改版误算成 M4 单 Agent 已完成。
