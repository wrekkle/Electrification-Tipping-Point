# R4 文献与审查（lit/）索引

类型: 目录索引  
状态: 生效  
负责人: cost-data  
日期: 2026-10-31

路径说明：任务登记的写范围是 `research/round4_2026-10-31/lit`（下划线+连字符），与 Lead 消息里的 `research/round4_20261031/` 不一致；本单按**任务登记写范围**落盘。若 Lead 需要统一为 `round4_20261031`，请合并/改名时保留本 README 的相对链接。

| 文件 | 内容 |
|---|---|
| N2_M07_identity.md | N2 与 M07 同文判定：题名/PII/DOI/作者/卷期四重一致（确定） |
| N1_M18_fulltext_access.md | N1=M18 身份；8 条合法获取尝试：403/付费墙/无 OA 副本；只拿到摘要（确定/UNVERIFIED 分清） |
| M06_M07_M18_comparison.md | 决策/信息/约束/目标/验证逐项对照；区分产权或供应链共享、车位共享准入、预约滚动匹配 |
| round3_claims_audit.md | 第三轮主张逐条审查：Δk 范围、分母与百分点、成本判词、聚类区间、C 同分/D 角点、固定 k 锚点 |
| access_log.jsonl | 本轮 10 次访问尝试的 URL/HTTP 状态/结果 |
| audit_round3_claims.py | 审查复算脚本（只读 round3 results） |
| round3_claims_audit.json | 复算证据（curves/deltas/fixed_k/tune_C/tune_D/validation/hidden_positive_cells） |

复跑：

    C:\anaconda\python.exe research/round4_2026-10-31/lit/audit_round3_claims.py

机制小算例见 ../mechanism/README.md。
