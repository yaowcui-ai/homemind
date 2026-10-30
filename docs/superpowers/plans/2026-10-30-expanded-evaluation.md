# Expanded evaluation implementation plan

**Goal:** 扩充真实评测覆盖，以实际失败驱动调优，并交付Docker/GitHub与简历证据。

**Architecture:** 复用原合成家庭、预测oracle、预算和执行核验。新增分阶段冻结入口，隔离Git版本提示，记录预定多轮补答与语义审计，不重写产品架构。

**Tech Stack:** 既有Python/FastAPI/LangGraph/DeepSeek、React、MySQL、Docker Compose。

- [x] 编写24开发/12新验证案例和分母、优先级、金标、补答；评审六类覆盖，冻结前离线验证可行性。
- [x] 先写scripts/tests/test_product_eval_expanded.py覆盖默认零联网、调度120次、360预算、变量目标评分、多轮补答和版本隔离，观察RED。
- [x] 推广d4/d5目标评分的固定26为金标值；给fixture增加可选配置回调，不改旧用例默认语义。
- [x] 新增scripts/product_eval_expanded.py：冻结初态/协议→baseline→candidate冻结→candidate→holdout，共用新账本；原记录追加写，孤儿请求拒绝重放。
- [x] 跑受控模型与oracle预检，冻结源码/案例/金标和授权文件，再运行基线48次真实开发任务。
- [x] 逐例诊断真实失败，最小修改提示并跑必要回归；候选源码固定后同48次定向复测，最后24次新题验证，不按结果改题。
- [x] 将语义核对与原评分分开、保留拒绝/失败/未知用量，导出不含账户信息的逐例证据和真实报告。
- [x] 更新README、接续、路线、唯一AI全栈项目MD；重建Docker并核对原家庭、配置和登录保留。
- [ ] 扫描提交内容/历史，正常推送GitHub，查看实际CI结果，交付准确的规模、前后对比和调优方法。

追加授权：X24/X21四补测16请求，另冻结Z12×S1/M24运行60请求；主测284不改，总360封账。[实际报告](../../product/expanded-evaluation.md)。
