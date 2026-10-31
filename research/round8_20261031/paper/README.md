# rev5 稿件构建骨架（第 8 轮，C 稿线）

类型: 研究记录（构建骨架说明）
状态: 阶段 1 骨架可运行；正文与数字待阶段 2
负责人: figure-c
日期: 2026-10-31

## 文件

| 文件 | 作用 |
|---|---|
| build_rev5.py | 构建 rev5 正文（--doc main）与 SI（--doc si）；默认 skeleton 模式 |
| content_rev5.py | 章节结构、正文骨架、{{数字占位}} 的解析规格、图/表计划、参考文献表 |
| evidence.py | 把每个 {{token}} 解析到 experiments/ 机器输出的文件/行/列，记录 sha256；解析失败即列清单 |
| 构建产物 | Electrification_tipping_point_v2_draft_rev5.docx、…_supplementary_rev5.docx、build_rev5_*_manifest.json、evidence_rev5_*.json |

## 结构（硬性，构建时校验）

问题 → 模型 → 方法 → 数据 → 结果 → 讨论 → 复现，对应 content_rev5.REQUIRED_SECTIONS 的 7 个 h1，
顺序固定；之后才是 References、Data and code availability、Ethics declarations。
SI 为 S1–S7（数据与 QA、假设与识别边界、敏感性、能量台账、基线与离线界、复现命令、v1 历史模型只读）。

## 两种模式

- skeleton（默认）：只验证版面与追溯管线。文档首段是 SKELETON 警告；每个数字显示为
  [UNRESOLVED:token]；不插入任何图（只写 F1 NOT EMBEDDED 占位行），不产生任何经验结论。
  占位表题注写明 [SKELETON PLACEHOLDER, not a result]。
- --real（严格）：以下任一条件不满足即拒绝保存（退出码 1）：
  1. 每个 {{token}} 都能解析到 experiments/ 的输出（文件存在、行与列匹配）；
  2. 每张计划图在 figures/FIGURES.json 中 status=real，PNG 存在；
  3. 文档中不含 TBD/SKELETON/UNRESOLVED/placeholder 等占位串；
  4. 章节结构正确。
  构建清单记录：每个数字 → 值 → 文件 + 行号 + 列名 + sha256；模板与输出的 sha256；字数与字符数。

## 数字追溯规则

- 正文与 SI 不写手填数字。所有经验数字写成 {{token}}，token 在 content_rev5.NUMBER_SPECS 中定义
  （file/column/where/agg/fmt/unit），由 evidence.py 读机器输出。
- 读不到就是 [UNRESOLVED:token] 并列清单，不得用旧稿数字、估计值或占位数字填充。
- 图的追溯在 figures/FIGURES.json（图→脚本→输入文件→字段/行）；正文图号只引用 F1–F7，
  图本身不带旧模型数据。

## 不覆盖保证

build_rev5.py 打开模板（rev4）只读：只复制样式与页面设置，正文清空后新写。输出路径若等于冻结投稿版
或 10-29/10-30/round6/round6_rev2/rev3/rev4 任一旧稿，直接拒绝；已存在输出需 --force。
默认输出到本目录，不写 paper/draft（阶段 2 定稿时再显式 --out paper/draft/… 并登记 SECTIONS.md）。

## 阶段 2 待办（依赖 B 的机器输出）

1. 用真实 CSV 核对 NUMBER_SPECS 的 file/column/where（列名以 B 的输出为准，不猜）；
2. 按 E1–E7 结果写正文与 SI，保留「未达标如实报告」的口径；
3. 填 REFS（从 rev4 bibliography 逐条核对，不新增不存在条目），再开引用编号检查；
4. python build_rev5.py --doc main --real + --doc si --real，通过后统计字数与页数：
   - 字数：python scripts/paper_stats.py --manuscript <docx>（默认只打印；SI 无 Abstract 标记，
     该工具按配置不适用，改用构建清单与 Word COM 统计）；
   - 页数：pwsh -NoProfile -File research/round8_20261031/paper/pagecount.ps1
     （Word COM：打开只读副本 → Repaginate → ComputeStatistics(2) → ExportAsFixedFormat PDF）。
     本机已装 Microsoft Office 2019，2026-10-31 实测可用。

## 阶段 1 实测记录（2026-10-31）

| 命令 | 结果 |
|---|---|
| python build_rev5.py --doc main --force | skeleton；74 段、1 表、构建清单 1439 英文词、13 个未解析数字 token（预期） |
| python build_rev5.py --doc si --force | skeleton；16 段、7 个 S 节、0 个未解析 token |
| python build_rev5.py --doc main --real --force | 拒绝：exit 1，written=false，13 token 未解析 + 7 图无 real 溯源，原 skeleton 文件 hash 未变 |
| python scripts/paper_stats.py --manuscript <rev5.docx> | S0–S7 合计英文词 921；表格内 10 词；题注 0；未归类段落 22（新 7 段结构与稿件 S0–S7 口径不同，阶段 2 需按最终结构核对） |
| pwsh -NoProfile -File pagecount.ps1 | main 6 页 / Word 统计 1389 词；SI 2 页 / 256 词；导出 rev5_main_skeleton.pdf、rev5_si_skeleton.pdf |
| python scripts/check_all.py | exit 0；错误 0；警告 8 条均为既有历史记录，与本次新增文件无关 |
