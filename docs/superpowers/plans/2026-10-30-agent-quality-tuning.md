# Agent 质量定向调优

目标：按真实失败修正阶段提示、减少重复推理输入与读取，让简历描述有实际改善依据。沿用现有LangGraph架构、严格schema、候选/确认/执行核验；不重写产品，不用放宽门禁或延长期限改善成绩。

证据：D5 A12混淆偏好排序与硬约束放宽；A11出现泛化恢复提示/建议忽略未知读数；A07的Plan.temperatures漂移；A02/A04含实际专家超时，A02重复另有extra_forbidden。旧成绩和原件保留。用户已明确授权定位与调优；本轮在codex/agent-quality-tuning原目录进行局部修复，保留此前未提交的简历修改。

- [ ] 跑D2/D3现有基线；用公开原件定位每种失败，区分模型超时和格式错误。
- [ ] 先增回归：上下文精简不丢当前事实、辅助未知读数可定位、Goal到Plan固定字段一致、最终阶段不再调用重复读取工具、非法工具仍拒绝且0动作。观察RED。
- [ ] 新增agent/prompts.py集中构建预测阶段提示，标准助手提示不动；区分优先级澄清与硬冲突，删除泛化缺失读数反例，提供精确Plan字段契约与完整Advice格式。
- [ ] 在graph/pipeline接入；只删除不参与决策的recent_events，保留原文、所有当前设备/房间/故障/主读数、偏好、全部候选与数值。最终选择使用已提供事实，关闭重复工具读取；预算和安全校验不变。
- [ ] 将原依赖重复读取来耗预算的实验测试改为真实的新调用路径；保留标准工具循环和原子预算覆盖。跑相关测试、完整后端及静态检查，记录输入长度与实际发出调用，不把离线受控模型当语言能力证据。
- [ ] 准备固定的旧版本/候选成对真实复测及新样本，冻结版本/输入/金标/初态和调用上限。旧D5已公开并用于开发，不再称未见集。当前没有新的付费请求授权，旧22余额不转用。
- [ ] 改写简历两条：保留解决的问题、方法和实际结果；移除调用上限/小批次数等调试说明。新的效果数字只能来自实际运行。

涉及文件：backend/src/homemind/agent/{prompts,graph,pipeline}.py、backend/tests/test_product_d6_quality.py及D2/D3预算用例；后续评测入口另列范围，不覆盖旧账本。验证命令：backend目录`.venv/Scripts/python.exe -m pytest tests/test_product_d6_quality.py tests/test_product_d2.py tests/test_product_d3.py tests/test_product_d4_followup.py -q`，随后`pytest -q`、`ruff check .`、`ruff format --check .`。
