# 图件盘点（R8-C，第 8 轮）

类型: 研究记录（图件盘点）
状态: 阶段 1 完成；阶段 2 待 B 的机器输出
负责人: figure-c
日期: 2026-10-31
范围: 原稿与历版图件清点、可复用性判断、与第 8 轮 F1–F7 的对应关系

## 0 结论先说

- 原稿的 8 个图文件都在 research/electrification/image1.png–image8.png，与冻结投稿版
  main_paper/Electrification tipping point_manuscript 202603submit.docx 里 word/media/image1.png–image8.png
  逐字节相同（sha256 一致，见 §2），共构成 5 个编号图（Fig.1–Fig.5）。
- 这 5 个编号图的数值全部属于 v1 的 PSC/PPR（车位—充电桩比例）模型，没有一个是第 8 轮整数 k
  服务约束模型的结果。按硬规则「旧图属于旧模型，不得改标签冒充新结果」，8 个文件全部不得作为
  新结果图复用；只有 4 种表达方式（结构）可借用。
- 第 8 轮需要的是 PLAN.md §4 的 F1–F7（E1–E7 机器输出）；这 7 张图与旧图没有一一继承关系。
- docs/reports/ 目录不含图件（.png/.jpg/.svg 均为 0 个；glob docs/reports/*.png 返回空），
  报告是 md/json 文本，因此无可复用图。
- 旧图共同的版式缺陷（对照新规则）：分辨率元数据 96/100/220 dpi（低于 300）、无矢量源（无 SVG/PDF）、
  Fig.2/Fig.5 用 jet/浅蓝配色（灰度与色觉障碍下不可读）、无样本量 N 与统计单位说明、
  Pnc/Plc、s=0.4 等缩写未在图内定义。

## 1 证据与方法

| 项 | 做法 | 结果 |
|---|---|---|
| 图件位置 | glob research/electrification/*.png | 8 个文件 image1–image8 |
| 原稿内嵌图 | 解压 docx 取 word/media/* 并算 sha256 | 8 个媒体文件与上面 8 个文件一一对应 |
| 编号图归属 | 按 document.xml 元素顺序定位图片段落，再取其后 Caption 段 | image1→Fig.1；image2→Fig.2；image3/4/5→Fig.3 a/b/c；image6→Fig.4；image7/8→Fig.5 四联 |
| rev4 工作稿 | 同一 sha256 比对 + inline shape 计数 | 8 个媒体文件仍在包内，但正文只保留 Fig.1（1 个 inline shape，1 条 Fig. 题注），Fig.2–Fig.5 未使用 |
| 图件格式 | Pillow 读实际格式/尺寸/dpi | 全部 PNG；dpi 元数据 96/100/220；无矢量源 |
| docs/reports 图件 | glob docs/reports/* | 仅 .md/.json，无图 |
| 其他 png | glob **/*.png | 其余为稿件逐页渲染（research/round6_20261031、research/manuscript_revision_20261031）、PDF 页截图与 tmp 截图，不是科研图，不进盘点 |

## 2 八个图文件（事实）

| 文件 | 尺寸 px | dpi 元数据 | 字节 | sha256 | 归属 | 内容 |
|---|---|---|---|---|---|---|
| image1.png | 1163x411 | 95.99 | 76096 | 458445592faa0d7fe6652eab3f3284d0c8f4a4676cd9b76c6ba4c101317420a7 | Fig.1 | PREI 问题概念示意：ICEV 与 EV 两组云朵、充电桩/电网、运营商；ICEing 现象 |
| image2.png | 1149x914 | 95.99 | 317403 | ee1c9fb3a85c93eef1c2dd846df83fc5c21723ad9bbc7988ef1b44d5f461e795 | Fig.2 a–d | PSC–PPR 曲线（两种稀缺度）、PSC 分量条形、最优 PPR 随 EV 比例（含 vacancy/leaving rate 系列） |
| image3.png | 1600x1000 | 99.99 | 100699 | 9afbfd4d6e3b7fa65bda8e7a6e9a8d7fdd0d0766cc9cebf5153d723a486ccb79 | Fig.3 a | 相对 baseline 的 PSC 变化（Pnc/Plc 两栏、±% 发散条） |
| image4.png | 1600x1000 | 99.99 | 151447 | f98d406d1780c17c8ea58575cd865019a32cc6246714eabb88c99ee2176dacc6 | Fig.3 b | 相对被动策略的 PSC 损失避免比例（Pnc/Plc 两栏） |
| image5.png | 1600x600 | 99.99 | 71094 | a3bde885762593113d973e21a29f6995ff673f6d7f053e7c2ec9c2e6604439cd | Fig.3 c | 情景 × EV 比例的最优 PPR 热图（Pnc/Plc） |
| image6.png | 1600x1000 | 99.99 | 83824 | ab9f1e3119d32c368d2f1ed39e18e2d6bda3f27d8579d14a26abc07f6eff17dd | Fig.4 | 运行模式（baseline / s=0.4 / s=1 / overhead）下 PSC 变化与 PPR |
| image7.png | 1144x892 | 95.99 | 459843 | 57beb3e3cb84a8f0d9df973ebb8053955d03713df872655e49e066fd513a2aeb | Fig.5 a–c | EV 比例 × PPR 的 PSC 热图（两稀缺度）、ETP 敏感性条形 |
| image8.png | 1137x649 | 219.99 | 91973 | 460eee7f6a9cc9419a74fa74198acf0ae6075860fedbbe0e5757309f8544186c | Fig.5 d | ETP 随 vacancy→leaving rate 的折线（多情景） |

## 3 可复用性判断（表达 vs 数据）

判断口径：数据是否属于本轮模型。属于 v1 的 PSC/PPR/ETP 输出 → 数据不可复用；版式是否值得借用 →
表达可复用但必须在 figures/style.py 下重画（矢量、300 dpi、色觉安全、N 与单位）。

| 旧图 | 内容 | 旧模型依赖 | 可复用表达 | 处置 |
|---|---|---|---|---|
| Fig.1（image1） | PREI 问题示意 | 概念图，不是数值结果；但框架绑定 v1 的 PSC/PREI 表述 | 四类利益方 + 物理元素的示意版式 | 若 rev5 保留问题框架示意图，按 figures/style.py 重画矢量版；不得直接把位图放进新稿冒充新图。R8 的 F1–F7 不含概念图，暂不重建 |
| Fig.2（image2） | PSC–PPR 曲线、分量条、最优 PPR | v1 PSC 优化（连续 PPR 决策） | 多面板 a–d 编排；最优解标记点 | 不复用数据。新模型是整数 k + 服务约束，由 F2（k–服务率）替代 |
| Fig.3a/b（image3、image4） | 敏感性（±20%/极值）PSC 变化、损失避免率 | v1 参数敏感性 | 发散横向条 + 数值标签 + baseline 参考线 | 不复用数据。若 R8 做参数敏感性，按同版式进 SI；主图由 E2/E4 决定 |
| Fig.3c（image5） | 情景 × EV 比例的最优 PPR 热图 | v1 最优 PPR | 离散格热图 + 单元格数值 | 不复用数据。可作 SI 敏感性热图版式；数据只能来自 E3/E6 机器输出 |
| Fig.4（image6） | 运行模式对比（s、overhead） | v1 模式集合，R8 设计矩阵无对应族 | 类别 × 变化% + 最优值 条图 | 不复用。R8 没有 overhead/s 模式实验，该图整体淘汰 |
| Fig.5a–c（image7） | PSC 热图 + ETP 敏感性 | v1 ETP（电气化拐点） | 二维热图 + 敏感性条形 | 不复用数据；ETP 不是 R8 的结论对象，不得把旧 ETP 改标签当新结果 |
| Fig.5d（image8） | ETP–vacancy/leaving rate 折线 | v1 ETP | 多情景折线 + 末端标注 | 不复用。仅在讨论 v1 历史模型时引用旧图并明确标注 |

## 4 第 8 轮图组（PLAN.md §4）与旧图关系

| 新图 | 对应族 | 机器输出（DESIGN_MATRIX outputs） | 与旧图关系 |
|---|---|---|---|
| F1 | E1 | coverage.csv, fit_metrics.csv, fit_params.json | 无旧图对应，全新 |
| F2 | E2 | curve_E2.csv | 取代旧 Fig.2 的 k—服务率角色 |
| F3 | E3 | search_E3.csv | 无旧图，最小性分类全新 |
| F4 | E4 | test_E4.csv | 取代旧 Fig.4 的规则比较角色（新基线集） |
| F5 | E5 | info_E5.csv | 无旧图，信息条件逐流比较全新 |
| F6 | E6 | energy_E6.csv | 无旧图，能量/功率/馈线全新 |
| F7 | E7 | traj_E7.csv | 无旧图，单实例非单调轨迹全新 |

图数服从解释需要：主图 F1–F7 只在对应族有完整机器输出且 E 族被正文引用时生成；没有输出的图不画、
不用占位图代替。运行时/规模曲线按 PLAN 进 SI。

## 5 已落地的统一规则（figures/style.py）

- 语义色板（Okabe–Ito 派生）+ 形状/线型随系列同时变化，灰度打印不丢信息；
- 单位写进轴标签：k=berths、失败率=%、能量=kWh、功率/馈线=kW、停留时间=min；
- 统一容差参考线（alpha = 5%，来自 DESIGN_MATRIX service_standard.default_alpha）+ 达成/未达成文字；
- 每图必须有 N 与统计单位脚注（site-day、independent stream 等），区间不是样本量；
- 边界/删失用专门标记（开口 chevron grid truncated、叉号 censored、缺失格 hatch），不静默截断；
- 输出 PNG ≥300 dpi + 同名 SVG（可编辑文字）；save() 复核 dpi，低于 300 直接失败；
- 溯源：每次保存把 图→脚本+sha256→输入文件+sha256+行数+字段 写入 figures/FIGURES.json（真实）或
  figures/FIGURES_DEMO.json（占位，永不写 FIGURES.json）；占位图带可见水印
  PLACEHOLDER DATA - NOT A RESULT (demo mode)。

## 6 阶段 1 产物与状态

- figures/style.py、figures/f1_data.py–f7_trace.py、figures/build_figures.py；
- python build_figures.py（demo）实测：7 张 PNG 300 dpi + SVG，FIGURES_DEMO.json 已写，
  FIGURES.json 未创建（demo 不碰真实溯源文件）；
- 真实图（status=real）尚未生成：research/round8_20261031/experiments/ 目前不存在。UNVERIFIED：
  R8 的图能否按上述字段契约落地，取决于 B 的机器输出列名；契约不匹配时先改 loader 再画图，不猜字段。
