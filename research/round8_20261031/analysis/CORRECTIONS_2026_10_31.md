# R8-F 更正记录（Phase3 复验后，2026-10-31）

1. site_audit.csv：原实现用"同时间戳先加成到达"的瞬时扫描，5 个站出现 max_concurrency>n_spaces 但
   minutes_above_capacity=0.0 的自相矛盾（VM 40>35、Hyatt 18>15、Drummond 34>33、Princes 15>12、Titles 18>17）；
   且 events 计数含 2 条纪元缺离场坏行。已改为同刻先离场后到达的净区间扫描并剔除坏行：
   10/10 站 max≤n_spaces、超容量分钟 0.0；VM 24,891、Hyatt 14,295 与契约一致。
   FIT_FOR_MODEL.md §2 的成因表述同步更正（不是"缺离场记录假象"，是同一分钟换车的排序效应）。
2. SCENARIO_LEDGER §1 已更正：run_meta 的 0.1/4/0.5 是未生效默认值；实际硬件=契约声明
   （charging_bays=connectors，feeder=connectors×kW；main22 强制 22 kW、feeder=k×22）。
3. M2 note 中"ICE 停车失败均 0/4643"不准确：B1 为 0，B2 在 2 条流上共 8 次 ICE 停车失败（分母 4,643）；
   能量与容量指标两规则仍 20/20 相同，B2 差异只体现在停车结果与 admitted/rejected 计数。
4. run_meta 的 parameters 块应加 effective_hardware 字段以免再被误读；本目录 hardware_audit.json 已提供
   逐站解析值与代码行号，作为当前证据。