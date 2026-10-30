# Agent 质量定向调优

目标：按真实失败修正阶段提示、减少重复推理输入与读取，让简历描述有实际改善依据。沿用现有LangGraph架构、严格schema、候选/确认/执行核验；不重写产品，不用放宽门禁或延长期限改善成绩。

证据：D5 A12混淆偏好排序与硬约束放宽；A11出现泛化恢复提示/建议忽略未知读数；A07的Plan.temperatures漂移；A02/A04含实际专家超时，A02重复另有extra_forbidden。旧成绩和原件保留。用户已明确授权定位与调优；本轮在codex/agent-quality-tuning原目录进行局部修复，保留此前未提交的简历修改。

- [x] D2/D3基线75通过；复用原件定位，区分超时、证据引用和目标字段漂移。
- [x] 新增7项数据契约/图边界回归，实际RED后GREEN；非法工具保持0动作。
- [x] 分阶段提示、软偏好澄清、辅助读数定位、Plan字段契约与Advice格式已接入。
- [x] 去掉recent_events和重复工具读取，保留所有当前事实和原门禁；专家只读且并行。
- [x] 调整旧耗预算用例以覆盖真实新路径；完整后端329passed/7条件skip、根脚本82passed、浏览器17passed、静态通过。
- [x] 用户授权80次，固定32运行74请求；原件/新4场景及版本先冻结。另明确授权原80内A09/S1补测一次，实际1请求通过。总75，余5停止；旧余额未用。首版回归不从原评分删除。
- [x] 完整简历与项目MD仅改两条为可靠执行和实测调优成果；目标提取Token约少33%、6组M 3/6→6/6，范围写明。Word仍一页，私有桌面文件不入库。

涉及文件：backend/src/homemind/agent/{prompts,graph,pipeline}.py、backend/tests/test_product_d6_quality.py及D2/D3预算用例；后续评测入口另列范围，不覆盖旧账本。验证命令：backend目录`.venv/Scripts/python.exe -m pytest tests/test_product_d6_quality.py tests/test_product_d2.py tests/test_product_d3.py tests/test_product_d4_followup.py -q`，随后`pytest -q`、`ruff check .`、`ruff format --check .`。
