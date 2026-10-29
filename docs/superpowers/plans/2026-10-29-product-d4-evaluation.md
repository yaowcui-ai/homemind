# D4：最小真实开发对照 Implementation Plan

> **For agentic workers:** Use executing-plans task-by-task; retain independent evidence and verify before completion. Reuse existing tooling and do not add UI/infrastructure.

**Goal:** 用6类开发场景比较S1/M，定位真实Bad Case，并只对有证据的问题做单因素调优。

**Architecture:** 复用product_eval的合成账号、官方HTTP隔离、持久预算与写新原件工具。新增D4入口，SQLite精确备份给成对S1/M，AB/BA交替；人工GoalContract仅评分端可见，同候选排序、程序执行后实际核验。默认只列案例、不读配置或联网。

**Tech Stack:** 现有Python/FastAPI/TestClient/LangGraph/SQLite/pytest，无新增依赖。

依据D1设计和product-d-evaluation-design.md；用户本轮“开始下一步，避免不必要步骤”授权D4实现，随后明确“允许，最多40次真实请求”。固定output/product-d4-real-20261029/budget.json共享账本，失败亦计数；不转用C2余量。基线74cec0f，独立项目原目录分支codex/product-d4-evaluation。

- [x] 新增6例开发输入/金标：20min硬期限、60min节能、60min舒适、强制低风不可行、半开帘/阅读灯保留、未知窗户首轮处置。最后一例仅首轮，不冒称恢复后的完整旅程。
- [x] 关键评分/同初态/预算/默认不联网测试先RED，再实现scripts/product_eval_d4.py与scripts/tests/test_product_eval_d4.py；不改旧批次账本上限。
- [x] 离线验证6对流程、实际候选和原选评分（含偏好次优照原选执行），保存输入/初态/模型配置/源码hash及失败；已获最多40次新真实请求授权，含首次批次与有限修复复测，硬止且不复用C2余量。剩余不足6次不开始新单轮任务，避免发送中途耗尽后混淆程序计数与真实请求；未运行明确列出。
- [x] 获授权后才运行真实S1/M；保存每次原选/动作/核验/耗时/用量，金标不传模型。无改进如实写，不为调优而改提示词。
- [x] 如有真实问题：定位理解/预测/专家/门禁/执行/评分，必要业务RED后只改单因素，同条件复测，不覆盖首次结果。
- [x] 针对改动做必要回归并更新评测报告/迭代/README/路线/接续，仅本地提交，不自动做D5或扩预算。

## 首轮实际交付

真实37/40（首次29+DD02复测8），余3停止。原评分与audit-v2分开：S1原3/6→审计4/6，M原2/6→审计3/6，这不是模型提升。DD05/M原任务禁用模型续验0新请求，DD06/S1为明确非独立的助手语义复核。唯一应用改动是共同数值排序提示；DD02各一次复测通过，不外推总体提升，M服务恢复不归因prompt。

相关后端132passed、根脚本51passed、Ruff/format过，原始失败/评分勘误留存，未改前端或数据库。独立评测/审计审阅批准。[报告](../../product/product-d4-evaluation.md)、[逐例结果与哈希](../../../evaluation/results/product-d4-20261029.json)。下一次优先定位DD01/M建议、DD05/S1漂移、DD06/M格式三类遗留，新模型批次另授权，未清理前不跳D5独立集。首轮交付不代表三类问题已修复。
