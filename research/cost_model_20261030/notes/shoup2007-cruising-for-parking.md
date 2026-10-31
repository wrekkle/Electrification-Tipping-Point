# Shoup, "Cruising for Parking"（ACCESS 30, Spring 2007 版）

状态: 草案
文献编号: P36（2026-10-30 由 paper-lit 按 literature/README.md 正式登记；索引 worker 生成，见 literature/index.json）
版本: ACCESS Magazine, Number 30, Spring 2007, pp.16–22（注意：不是 Transport Policy 13(6):479–486 的 2006 期刊版）
读的范围: 第 17 页（p.2 of 12 页扫描）目视核读；其余页未读

## 为什么拿到的不是 2006 版
免费全文来自 fbfl.us（市政公开转载），共 12 页扫描件、无文字层。第 17 页页脚印
"ACCESS / NUMBER 30, SPRING 2007"，故这是杂志版。任务里写的 Shoup(2006) 期刊版
（Transport Policy）本次未取得全文，索引不得登记为已读。

## 读到的数（p.17 正文 + Figure 1 表）
- 1927–2001 年间 16 项巡游研究，11 个城市 CBD、4 个大洲。
- 平均「找到路边车位」耗时 8 分钟（正文）；Figure 1 平均值 8.1 分钟。
- 平均约 30% 的通过车流是巡游找车位（Figure 1 AVERAGE 30%）。
- 示例推算：3 分钟找位、每车位每天周转 10 车 → 每天每车位 30 分钟额外行驶；
  10 mph × 0.5 h = 5 VMT/车位/天；1,825 VMT/车位/年。
- Figure 1 区间极端值：Freiburg 1977 巡游占比 74%；New York(3) 1993 平均 13.9 分钟。

## 可复用点
- 停车失败成本的「搜索时间 × 时间价值 + 巡游里程 × 单位里程成本」结构。
- 巡游占比可作敏感性分析的场景参数（但必须标外地/路边停车，非台北路外停车场）。

## 局限与风险
- 全部为路边停车（curbside）样本，台北案例是路外停车场（off-street），机制不同。
- 样本时间跨度 1927–2001，无台北数据；不得当台北参数。

## 与本项目的关系
COST-MODEL-V2 §3 油车无法停车：Δt_搜索 的文献机制依据；费用结构的敏感性分析。

## 证据位置
- p.17（ACCESS 页码）内文 "The average time it took to find a curb space was eight minutes,
  and about thirty percent of the cars in the traffic flow were cruising for parking." + Figure 1 表。
- 本地文件（登记后已移入既定 PDF 目录）: research/ev_parking_math_20261029/PDFs/P36_Shoup_Cruising_for_Parking_ACCESS30_2007_reprint.pdf
  SHA-256 d4f39f6365a37d3d496ae44892cfa40aa2ea124fa3ad1093341b8fc02ffa2f1b，12 页
- 渲染页: research/cost_model_20261030/downloads/png/page02.png（p.17）
