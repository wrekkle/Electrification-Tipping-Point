# 第六轮 C 论文工作稿：构建与检查记录（第一阶段）

状态: 第一阶段完成（结果与讨论待 Q1-Q3 结果回填）
日期: 2026-10-31
范围: 新工作稿、构建脚本、表格生成器、统计与渲染检查；未改 main_paper、paper/draft 旧稿、前五轮证据。

## 1 产物与哈希

| 文件 | 含义 | SHA-256 |
|---|---|---|
| paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6.docx | 新工作稿（Word） | 830591ce7e097f1f0803e4719644fe92f141e0e3d07d4b7ef8b34c3b07fcd1d3 |
| paper/draft/build_paper_v3_round6.py | 构建脚本 | e41ee1e5cb2689f24ef329a373e9509b7331d4c381e0467126f62d361ccf04ad |
| paper/draft/paper_v3_round6_content.py | 静态内容（题名/摘要/章节改写/新参考文献） | 502cb130b8869ca4769686b32089b438f3dda54cca3e0afd4f0fc16266a59f7e |
| research/round6_20261031/c_paper/make_tables.py | 表格生成器（从机器 JSON 读计数） | a7a91488d37dd29497f8bf0655dffc3459b5188fc8b46550e2ecf90a7a9233ab |
| research/round6_20261031/c_paper/tables_v3.json | 表格规格（含输入哈希） | 88b37ce907b577304d61ffaedabd83ce07c0d7ee6c9dbf5555f62d15a30b1537 |
| research/round6_20261031/c_paper/build_manifest.json | 构建清单（引用映射与检查结果） | d3e3e81943db4a47d951bca794d82fa601932ac013f50ac0895068d980a1ff17 |
| research/round6_20261031/c_paper/paper_stats.json | 字数统计报告（--out 产物为 Markdown 文本） | b1c129eab2a66670fed7ca058420212a82e400f74d0f469b769860a29ecd3e00 |
| research/round6_20261031/c_paper/round6_draft.pdf | Word 导出的 PDF（渲染检查用） | f6cd066576f7aff4f5edda8952e9b2c4a0c9599f2d2df8adbd8066501839f21c |

基线：paper\draft\Electrification_tipping_point_v2_draft_2026-10-30.docx，SHA-256 b026c0d5e33690b422f164a16c0c2847fedf890e35372bd95f28cf4d9f11f28a。

## 2 命令、解释器与退出码

| 命令 | 解释器 | 退出码 |
|---|---|---|
| python research/round6_20261031/c_paper/make_tables.py | C:/anaconda/python.exe 3.12.3 | 0 |
| python paper/draft/build_paper_v3_round6.py --force | DSH runtime python（python-docx） | 0 |
| python scripts/paper_stats.py --manuscript 新稿 --out research/round6_20261031/c_paper/paper_stats.json | DSH runtime python | 0 |
| Word COM ExportAsFixedFormat(..., 17) | Microsoft Word 16.0 | 0（54 页） |

构建时间戳 2026-10-31T08:28:53Z；解释器 C:\Users\tho25\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe | 3.12.14。

## 3 检查结果

- 引用双向核对（脚本内，失败退出码 1）：未解析标记 0；参考文献 76 条；正文未出现的编号 无；越界编号 无。
- 新增参考文献按首次引用顺序编号：{"M06": 72, "M07": 73, "M18": 74, "M08": 75, "M10": 76}（原稿 71 条，其后接 72-76）。
- 段落 272、表格 11、一级标题 7 个。
- 字数（脚本口径，非 Word 缓存）：英文词 15760；表格内文字 367 词、题注 108 词单独计数。
- 渲染检查：Word 16.0 打开并导出 PDF 54 页；Table 14 题注与表格同页（p19）；Table 13 题注在 p31 页脚、表格在 p32 页首，题注段落已设 keep-with-next，属排版待处理项。
- 未生成页面像素图：本机无 LibreOffice（office-render / office-export-pdf 技能不可用），anaconda 与 DSH runtime 均无 PDF 栅格库（fitz、pypdfium2）；改用 Word COM 查询页码与表格跨度，属结构性检查而非像素检查。

## 4 内容口径（第一阶段）

- 题名与摘要为初稿，结果句留 RESULT PLACEHOLDER；不写共享省枪、共享无效、社会最优、等价定理或普遍证明。
- 新写章节：Related work and positioning；Data, calibration, and scenario transfer；Service constraints and the integer configuration problem；Information conditions and admissible decisions；Integer provision under joint service constraints；Limitations and reproducibility。
- 旧稿 Results 的 v1 口径段落保留，新增 Results 小节明确两者不合并；旧稿 Discussion 的 ETP 段落未改，新小节不引其作为证据。
- 文献只用已核全文本或已登记来源：M06/M07/M18 依第五轮六轴对照页码（M18 在线附录证明未取得，只引模型结构）；M08 用 INL 表 1 计数；M10 仅检索索引转录并标 provisional。
- 表格由 make_tables.py 从 rates.json、charge_probability_sources.json、four_categories.json 读出，含分母、来源与识别状态；数值未手填。

## 5 UNVERIFIED 与待处理

- M10 作者名单与印刷页码未核（无本地全文）；正文标 provisional，条目留 author list to be completed。
- M18 命题证明在未取得的在线附录；正文只引模型结构与信息集。
- paper_stats.py --out 实际写出 Markdown 报告、文件名为 .json（按任务命令原样执行）；机器可读统计需另加 --json，本轮未执行。
- Table 13 题注与表格跨页，第二阶段排版处理。
- 成本参数（VOT 价格年、搜索/绕行时长、外部性、挪车成本、q_need）仍不可识别，正文不写社会最优。

## 6 第二阶段入口

1 收到 Q1-Q3 结果后写入 Integer provision 小节与 Discussion，替换两处 RESULT PLACEHOLDER。
2 摘要、题名、结论按最终证据改写，不升级投稿。
3 结果表继续由机器 JSON 生成，补分母、单位、样本、来源列。
4 重跑构建、paper_stats、Word 导出与页码检查。

## 7 第二阶段：Q1-Q3 结果整合（2026-10-31 追加）

状态: 第二阶段完成（题名/摘要/Results/Discussion/局限按最终证据改写；未升级投稿）

### 7.1 输入证据（只读）

- research/round6_20261031/b_mechanism/q1_traces.json SHA-256 099d4a61a3a2d98b2ca7a5aa01c0ffbbcb0161ae90b9bc5977298de75a3cc102
- research/round6_20261031/a_info/q2_info_regimes.json SHA-256 d878703f5f156d78da0a382433d7674f5da44bdd862e174f024be8357f805ef1
- research/round6_20261031/b_feasible/q3_feasible_sets.json SHA-256 600795d7beb3669f76cb9c44019bf5b10cbe2c1dd020a38607ede45febb6e454
- research/round6_20261031/a_semantics/recompute_59_curves.json SHA-256 e2b3579e9427ceba31ecfbbb9afcb107d27184b6921408255d157bf56ce8436a

### 7.2 产物（更新后）

- paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6.docx ｜ 新工作稿（294 段/14 表/76 文献） ｜ SHA-256 c83b6a2520be77c65885c93cff4079b4f4bc153605fd7e7739dacf66fae9a864
- research/round6_20261031/c_paper/tables_v3.json ｜ 5 张表规格（T13-T17，含输入哈希） ｜ SHA-256 71def5d061d3fdbc668e38ccff9191a195f1d68a8041c26009c7572b69b402f9
- research/round6_20261031/c_paper/build_manifest.json ｜ 构建清单（引用映射与检查） ｜ SHA-256 8d67c0844a0ce175f628c422ff82841a0871535c8bae5734e0df6d2977f03ea2
- research/round6_20261031/c_paper/paper_stats.json ｜ 字数报告（Markdown 文本） ｜ SHA-256 a86db1b8179ba39e9ca091e9af2020e3effe3c186026da5bf11a38b1a5326121
- research/round6_20261031/c_paper/round6_draft.pdf ｜ Word 导出 PDF（60 页） ｜ SHA-256 c096a69eef3b1a3251d03786e54066470083adc6fe19836c988ff36a943b1942

### 7.3 命令与退出码

- python research/round6_20261031/c_paper/make_tables.py（C:/anaconda/python.exe 3.12.3）EXIT=0；5 张表：T13 6 行、T14 2 行、T15 3 行、T16 4 行、T17 6 行。
- python paper/draft/build_paper_v3_round6.py --force（DSH runtime python）EXIT=0；未解析标记 0、越界 0、未被引用 0。
- python scripts/paper_stats.py --manuscript 新稿 --out research/round6_20261031/c_paper/paper_stats.json EXIT=0；标题摘要 346 词、Results 4185 词、Discussion 2204 词、合计 17186 词；表 14 张、题注 10 条、公式 65。
- python scripts/check_all.py EXIT=0（3/3 通过；警告均为历史文档旧计数，非本轮新增）。
- Word 16.0 COM ExportAsFixedFormat(...,17)：60 页；表 13-17 题注与表格同页（13:p38、14:p20、15:p21、16:p23、17:p24），无跨页断表。

### 7.4 写入正文的关键数字与出处

- Q1：三条最小轨迹 E1(n6,0->1) ICE 8->7、EV 5->7、EV 停普通位 8->2；E2(n8,5->6) 6->5、1->1、3->0；E3(n8,seed3,2->3) 9->8、4->5、9->5；控制变量 3/3 消失（禁回落、反选位、dwell-20%）；3456 格枚举 0 例下降（禁回落与反选位）。来源 q1_traces.json。
- Q2：656 次仿真 0 失败；8 单元 Δk 全负（-2..-17，中位 -9.5）；同 k 四类 143/26/61/98；k_min(I0) 下 2/8 仅 I0 可行（ICE 率 0.0769/0.1782）；16 个可行集全为区间。来源 q2_info_regimes.json。
- Q3：660 组完整 k=0..40；非空全为连续区间、断裂 0；inclusive 空 124、strict 空 139（差 15 组为 N/A 口径）；437 组截断；840 对：双方 677、仅第一 7、仅第二 4、均空 152；恢复可行 4、省设备 2、同 k 改善 4、同 k 变差 6、双方不相交 5；TPE0330 扩展首可行 52-84 标预算截断。来源 q3_feasible_sets.json。
- 语义口径：60 条曲线三约束 780/975（N/A 跳过）、765（严格）；四约束五态 66/975；旧全跳过 310、严格 51；310->51 为口径差，能量率保持删失辅助。来源 recompute_59_curves.json。

### 7.5 写作口径落实

- 摘要/题名/Results/Discussion 一致改写；正文无 Agent、轮次、任务编号与占位符（脚本检查 BAD=[]）。
- 不写共享省枪或无效：写成在测试模型与情景下未观察到系统性地减少所需设备数，并把 4 个恢复可行、2 个省设备单元格单列。
- 不把 Q2 写成信息必然改善或全局最优：明示启发式比较、包含关系是定义性质、同 k 下 26 格仅 I0 可行。
- Q1 只写受限结论：禁回落+升序选位下 ICE 失败集合随 k 非增（3456 格枚举 0 反例），声明不是普遍定理、轨迹为机制模型合成重放而非实测。
- Q3 不把有限枚举称普遍证明：空集/截断与严格-包容口径并列报告。

### 7.6 本轮未做与 UNVERIFIED

- 页面像素渲染未做：本机无 LibreOffice（office-render / office-export-pdf 不可用），anaconda 与 DSH runtime 均无 PDF 栅格库；渲染检查限于 Word 导出的页数、题注/表格同页与不跨页。
- M10 作者名单未核；M18 命题证明未取得（正文只引模型结构与信息集）。
- 旧稿 Results 的 v1 口径与 ETP 段落保留未改；新小节明确两者不合并。
- 未启动 RL、未扩城、未跑大网格；main_paper 与 10-30/10-29 旧稿 mtime 未变（check_all 通过）。

## 8 生产性修正在稿（2026-10-31，Lead 复核后）

状态: 5 项技术问题已修；无新增结果、旧稿与投稿版未动。

### 8.1 修正内容

1 生产性字符串清零：placeholder 0、to be produced 0、To be drawn 0、to be reassigned 0（构建脚本内置断言，非零即 EXIT 1）。
2 删除只有题注没有对象的 5 个条目（Fig. 6、Fig. 8、Table 9、Table 10、Table 11），并把正文引用改写为散文：Fig. 7 段改为“该检验只写入评价协议、本轮未计算，结果对象留补充材料”；Table 9 的类别—车位兼容性改写为按规则定义逐类陈述；v1 段与成本节不再指空表。保留 Fig. 1-5（有图）与 6 张数据表。
3 表号按首次引用重编：fixed-k 表=Table 1、机制轨迹=Table 2、I0/I1=Table 3、可行集对=Table 4、充电率来源=Table 5、成本参数=Table 6；首次引用段序 71/75/82/88/151/202 严格递增；删去 Results 内重复的“Table N gives the counts”引出编号与全部 to be reassigned 注记；Table 6 题注改为 Caption 样式。
4 参考文献计数一致：删除 base 稿遗留的 1 个空 Bibliography 段落，Bibliography 段落 76 = 非空 76 = 双向检查 76/76。
5 渲染：Word 16.0 导出 60 页；6 张数据表题注与表同页且不跨页（T1 p19、T2 p21、T3 p22、T4 p24、T5 p38、T6 p50）；Table 5/6 因表体较大加 pageBreakBefore 保证同页，页脚留白属本轮排版折衷，记入排版待处理。结论性说明：本机无 LibreOffice、anaconda 与 DSH runtime 无 PDF 栅格库，无像素级页面图。

### 8.2 证据与退出码

- 构建：python paper/draft/build_paper_v3_round6.py --force（DSH runtime python）EXIT=0；ops 27 条；输出 SHA-256 fc1320b7f6f0889e399681f9533f90b7cc2f29b1c32f7b58ffda4ca289ffb857。
- 统计：python scripts/paper_stats.py --manuscript 新稿 --out research/round6_20261031/c_paper/paper_stats.json，EXIT=0；总 17,007 词（S0 346、S1 2132、S2 4166、S3 2204、S4 6463、S5 1643）；图 8 张、表 14 张（6 数据表 + 8 公式表）、题注 11 条、公式 65、参考文献 76。
- 引用双向核对：76/76，越界 0、未引用 0、未解析 0。
- check_all.py EXIT=1，原因不在本稿：docs/TODO.md 8029>8000（超 29）、paper/SECTIONS.md 3235>3200（超 35），两文件 mtime 2026-10-31 16:44 非本轮写入，属 Lead 本轮文档更新；稿件字数与章节一致性、文献索引两项通过。
- 冻结件：main_paper 稿 mtime 2026/10/29 9:49:27、2026-10-30 工作稿 mtime 2026/10/30 21:01:21，均未变；未写入任何旧 Word 或已有交付 JSON。

### 8.3 仍未做

- 无像素级页面图（缺 LibreOffice/栅格库）；公式与表格的视觉溢出未经像素确认。
- Table 5/6 前置分页会造成页脚留白，正式排版时应由期刊模板处理。
- M10 作者名单未核；M18 附录证明未取得；旧稿 ETP 段落保留未改（已在正文说明不合并）。

## 9 二阶段修订（rev2 + 补充材料，2026-10-31）

依据: research/round6_20261031/lead/consistency_check.md（Lead 的逐项事实与建议原文）+ Lead 两条补充口径。所有数字来自机器记录，未新增实验。

### 9.1 内容修订（rev2 相对 rev1）

1 题名改为 Lead 指定版：Minimum integer charging provision in mixed-fleet parking: joint service constraints, an identifiability boundary, and conditional evidence on shared use and a charging-intention signal。
2 Table 4（T17）行标签区分配对类型：A vs B、A vs C、A vs D 为 dedicated vs shared；B vs C、B vs D、C vs D 为 shared vs shared。Note 改为 Lead 定稿文本（仅 A 行比较专用与共享；B/C/D 行是同信息条件下两条共享规则的分配次序效应；两个 smaller count 来自同一 TPE1376 seed 10 组；截断与空集分开报告）。
3 §2.9 正文明写：三行 A 行中共享规则 restore 0、smaller k 0；4 个 restore 与 2 个 smaller 全部来自 B|D、C|D，且是同一组的两个配对比较，不是两组独立证据。
4 Q2 统一为“一个具体的信息感知启发式”：补充其动作定义（充电到达优先带枪位、非充电到达优先普通位、ICEV 沿用原规则），删除“what the information could be worth”与信息价值解释，改为“this heuristic extracts from the signal / 两实现策略的算法比较”。
5 Q3 所有区间断言限定 within the enumerated range 0-40：摘要、§2.9、Discussion、结论、Limitations 同步；437 截断、空集 124/139、15 组 N/A 差异保留；TPE0330 52-84 仍作边界示例。
6 P1 改为“命题 + 六条假设 + proof in Supplementary Note S2”：删除 mirror coupling 依据与“枚举即证明”措辞；正文写明枚举与命题一致但不是证明替代、不主张新颖；控制与逐事件轨迹移 S3，证明与反例移 S2。
7 Limitations 的 “437 of the 660 groups in the second experiment” 改为 “in the feasible-set experiment”；新增一段：P1 假设与方向、两案例为同一组两配对、区间限定 0-40、437 为未知而非不可行、S1-S6 另有文件。
8 可复现段改为一句指针（脚本/哈希/审计细节移 S6），保留第二实现一致性数字（441 行、4.5e-12、145 检查）。

### 9.2 新增/另存文件

- 主稿 rev2: paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx（SHA-256 b2d36e2d01ffb9538eafa7d89f5efb9763019241204f826cb999736fe6db3c62，1388297 字节）。
- 补充材料: paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx（SHA-256 4811c540001188b62b7098696eaf8ce7fba5731b893cbbe076e52e1a4accbd1f，49950 字节，58 段、7 表、S1-S6）。
- 构建脚本另存: paper/draft/build_paper_v3_round6_rev2.py、paper/draft/paper_v3_round6_rev2_content.py、paper/draft/build_supplementary_round6.py、paper/draft/supplementary_round6_content.py。
- 机器表: c_paper/tables_rev2.json（T13-T17，T17 行标签与 Note 见上）、c_paper/tables_si.json（S1、S3a、S3b、S4、S5a、S5b、S6）、生成器 make_tables_rev2.py / make_tables_si.py。
- manifest: c_paper/build_manifest_rev2.json、c_paper/build_manifest_supplement.json；统计 c_paper/paper_stats_rev2.json；PDF c_paper/round6_rev2_draft.pdf（61 页）、c_paper/round6_rev2_supplement.pdf（7 页）；逐页 PNG c_paper/render_png/。

### 9.3 验收证据（命令与退出码）

- 构建主稿: build_paper_v3_round6_rev2.py --force，EXIT 0；289 段、14 表、引用 76/76（越界 0、未引用 0、未解析 0）、pending strings 全 0、表号 1-6 与图号 1-5、Bibliography 76=76。
- 构建 SI: build_supplementary_round6.py，EXIT 0；58 段、7 表。
- 统计: paper_stats.py --manuscript rev2 --out paper_stats_rev2.json，EXIT 0；合计  全部范围之和                  0     17402   111714  240   56。
- 导出与逐页检查: Word 16.0 ExportAsFixedFormat，主稿 61 页、SI 7 页；PyMuPDF 逐页栅格：空白页 0；文字越界 0（阈值：左右 40pt、上下 30/20pt，页脚带排除）；题注与表同页：T1 p19、T2 p21、T3 p23、T4 p24、T5 p39、T6 p51，S1 p1、S3a p4、S3b p4、S4 p5、S5a p6、S5b p6、S6 p7；6 张数据表与 SI 7 表均 start=end（不跨页）。
- 冻结件: 旧 rev1 主稿 fc1320b7…、投稿版 04bda311…、base 稿 b026c0d5… 的 SHA-256 与 mtime 均未变；本轮只读打开。
- check_all.py 仍为 EXIT 1，原因是 docs/TODO.md 8029>8000、paper/SECTIONS.md 3235>3200（非本轮写入）；稿件字数与章节一致性、文献索引两项通过。

### 9.4 仍未做/未核

- 无与期刊模板的像素级比对（本机无 LibreOffice，PDF 栅格用 PyMuPDF）；表格内 8.5pt 字号未与投稿模板核对。
- M10 作者名单仍为占位（provisional），M18 附录证明未取得；M06/M07 作者报告数值与本地复算仍分开。
- 证明为手写推导 + 枚举/随机流支持性检查，未做机器证明；命题只在 A1-A6 与 strict no-fallback 下成立。

## 10 rev3 最小补丁（task-9，2026-10-31）

三处改动，均在 rev3 与重建的 SI 中；rev2/rev1/投稿版未覆盖。

1 旧方法段（rev2 para 156，现 rev3 同位置）：删除 global optimum / invaluable / profound insights 三处辩护性表述，改为“枚举在有限网格上取到被评估点中的最好点，不对网格外作最优性断言；枚举记录目标值使验证可追溯成本项”。段末“Enumeration certifies optimality over the enumerated grid only”保留，与新增句合并去重（正文一处）。
2 旧讨论首段（para 95）：socially preferable 句加 “under the submitted cost model”，句末加 “This is a cost-based threshold under that model, not a claim that the configuration is socially optimal.”
3 SI S2 证明改为容量差耦合（Lead 给出的版本）：A5 改为“存在兼容空位即准入；空闲位选择不影响准入；同刻事件顺序相同；证明不使用最小号优先”；删除 dominance/排序占位论证，改用计数不变量 0 <= a-b <= 1，含离场、到达三种情形与矛盾排除；保留同址反例，并加一句“正确论证不需要车位级匹配，只需上面的计数差”；末尾枚举支持段写明“枚举与命题一致但不是证明、不宣称新颖”。主稿 P1 段由 “dominance coupling” 改为 “count-difference coupling”。

### 10.1 产物

- rev3 主稿: paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx（SHA-256 06906f34313f2156beebf1b5e1aa3e2d1d4f2a026fd2f2ffa502a0ccb1fe117a，1387829 字节）
- rev3 构建脚本: paper/draft/build_paper_v3_round6_rev3.py、paper/draft/paper_v3_round6_rev3_content.py；manifest build_manifest_rev3.json
- SI 重建（同文件名）: paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx（SHA-256 2ebc9e832123d5e9ff314220bd985803f84a6b880bed1fb6b9a07b1bd75579f5，49935 字节，58 段、7 表）
- PDF: c_paper/round6_rev3_draft.pdf（61 页，SHA-256 57d3e682549abc6a0d3f0fe9e95682f36e75d4495b5472a7f1c3ca1316cca3fc）、c_paper/round6_rev2_supplement.pdf（7 页，SHA-256 14bb7da0003638f7e8dd8fc4b6b9f40c4008bd4e83d8086ba72656cb1dc0982c）
- 统计: c_paper/paper_stats_rev3.json（合计 17,418 词、图 8、表 14、题注 11、公式 56）

### 10.2 验收

- 构建 rev3 EXIT 0：289 段、14 表、引用 76/76（越界 0、未引用 0、未解析 0）、pending strings 0、表号 1-6 与图号 1-5。
- 文本检查：global optimum 0、invaluable 0、profound insights 0；“best evaluated point within that grid” 1、“does not certify optimality outside the grid” 1、“under the submitted cost model” 1、“count-difference coupling” 1、dominance coupling 0。
- SI：新 A5 与计数不变式均存在；“mirror coupling” 仅出现在反例段（用于说明旧论证为何不成立）。
- 逐页栅格（PyMuPDF）：rev3 61 页、SI 7 页，空白页 0、文字越界 0；题注与表同页且不跨页（T1 19、T2 21、T3 23、T4 24、T5 39、T6 51；S1 1、S3a 4、S3b 4、S4 5、S5a 6、S5b 6、S6 7）。
- 未变：rev2 b2d36e2d…、rev1 fc1320b7…、投稿版 04bda311… 的 SHA 与 mtime；旧文件只读打开。

### 10.3 仍有

- SI S2 的证明为手写推导 + 枚举/随机流支持，未做机器证明；命题只在 A1-A6 与 strict no-fallback 下成立。
- M10 作者名单、M18 附录证明仍 UNVERIFIED；无期刊模板像素级比对。
