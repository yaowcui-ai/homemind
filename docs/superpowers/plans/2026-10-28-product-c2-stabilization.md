# 产品C第二轮实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task.

**Goal:** 定位被拒输出的错误字段，完善用户下一步并验证12个核心/改写场景。

**Architecture:** 保留单Agent、共享校验/执行器；诊断进入现有agent_run JSON，无新服务/迁移。独立合成评测复用首轮预算/评分辅助，共享本轮32次账本，保留旧批次不改写。

**Tech Stack:** Python/FastAPI/LangGraph/Pytest，React/TypeScript/Vitest/Playwright。

---

## 1. 拒绝诊断与用户反馈

- [x] `backend/tests/test_product_c2_diagnostics.py` 先固定无效澄清option/动作/keep/room/温度引用的失败字段及零写入，跨家庭不可解析、普通窗户未知不改成not_found、有动作任务不误称零动作；保留RED。
- [x] 修改 `backend/src/homemind/agent/validation.py`、`service.py`，必要时新增小的diagnostics模块，保存有限结构化校验依据，旧任务向后兼容。`pytest tests/test_product_c2_diagnostics.py tests/test_m4_agent.py -q`通过，Ruff通过。
- [x] 前端 `tasks.types.ts`/`tasks.validation.ts`/`TaskDetail.tsx` 按实际诊断提供下一步，折叠技术信息；组件和响应校验先RED再实现，旧详情可读，lint/TS/Vite通过。
- [x] 需要时新增受控浏览器验证一个无效引用失败反馈，不能把受控模型写成真实理解率；独立规格后质量审阅。

## 2. 案例与真实运行

- [x] `evaluation/product-c2-cases.json`：原四个失败原样复测+新增8例，期望冻结并标注开发用途。扩展现有评测helper支持预设自由回答，不改变原案例期望或原结果。
- [x] `scripts/product_eval_c2.py` / `scripts/tests/test_product_eval_c2.py`：先测试无授权默认零请求、固定批次、跨阶段共享32、旧40账本不动、源码/期望摘要和案例ID唯一、阶段2只选失败且不覆盖、C12/自由回答固定分母；先RED再实现。
- [x] 模型调用前冻结版本并检查来源/分母/预算，运行12例阶段1；每例立即保存。只在证据指向时做窄修，阶段2最多3失败案例用剩余请求同条件复测，所有请求累计≤32，原件不覆盖。
- [x] 实际诊断/程序事实与推断分开；旧C14具体输出未知不得追认；保存可移植结果摘要和源码/原件hash。

## 3. 验证与交付

- [x] 运行受影响后端/前端/脚本与必要浏览器检查，检查本项目MySQL是否需额外证据（本轮无迁移）。不因故障随意重建数据库/停止其他容器。
- [x] `docs/product/product-c2-evaluation.md`记录逐例、指标分母、Bad Case/优先级、修复及未证实结论；补PRD/验证方法/迭代/案例和README/接续/路线。
- [x] 根代理核验原件与摘要/本地链接、敏感值不进入Git；所有原始失败保留，仅本地提交当前阶段文件；结束停止，不做D/E。

## 实际交付

诊断/选项及Agent相关77passed，前端完整74（首阶段）、末次26定向+lint/TS/Vite通过；新增受控browser1通过，独立规格/质量批准。专用MySQL原5项回归5passed，无新迁移。脚本全33passed（含base15/C2十项）及Ruff/格式通过；全部RED/GREEN保留。

真实phase1=12例/24请求，冻结预期9通过+1oracle缺陷C06+2真实交互问题C12/C40；phase2两例同条件各复测一次通过，6请求。总30/32，余2不使用，旧40账本SHA未变。C06 low20min26.8/auto26.0勘误，没有改原件/评分/热模型；C14旧输出仍无法追认，C42后续回答未测。C40回复标记加did_reply门控，旧原件解释保留。

详见[C2报告](../../product/product-c2-evaluation.md)。下一轮D先设计最小多Agent分工、控制参数和新冻结样本，不自动执行D或调用余额。仅本地提交、不推送/合并/发布。
