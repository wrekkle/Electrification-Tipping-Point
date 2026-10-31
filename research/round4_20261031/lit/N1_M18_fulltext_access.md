# N1（TR-D 2025 144:104773）与 M18 全文获取记录

类型: 文献获取记录  
状态: 生效  
负责人: cost-data  
日期: 2026-10-31

## 结论（确定）

1. **N1 与 M18 是同一篇论文**：Chen Feng, Pavlov Valery, Zhao Sitao, Feng Jianghong, Xu Su Xiu, "Joint operation strategy of parking and charging infrastructure", Transportation Research Part D: Transport and Environment **144 (2025) 104773**, DOI [10.1016/j.trd.2025.104773](https://doi.org/10.1016/j.trd.2025.104773)。M18 是该项目给这篇论文的编号；literature/notes/M18-停车与充电基础设施联合运营.md 记录同一 DOI/卷/页。
2. **全文未取得（付费墙、无合法开放副本）**。可获得的最高层级是题录+摘要（BITA Pure 与 TRID 两处一致）；出版社版面（ScienceDirect）返回 403。未绕过任何访问控制，未使用影子图书馆。

## 尝试记录（合法公开途径；逐条）

| # | 途径 | URL | 结果 | 说明 |
|---|---|---|---|---|
| 1 | Crossref 元数据 | https://api.crossref.org/works/10.1016/j.trd.2025.104773 | HTTP 200 | 题名/作者 5 人/卷 144/文章号 104773/2025-07/PII S136192092500183X；license 仅 Elsevier TDM |
| 2 | OpenAlex 元数据+OA 状态 | https://api.openalex.org/works/doi:10.1016/j.trd.2025.104773 | HTTP 200 | `is_oa=false, oa_status=closed, any_repository_has_fulltext=false`；locations 仅出版社 landing page |
| 3 | Semantic Scholar | https://api.semanticscholar.org/graph/v1/paper/DOI:10.1016/j.trd.2025.104773?fields=title,abstract,openAccessPdf,externalIds | HTTP 200 | `openAccessPdf={url:"",status:null}`，`abstract:null`；提示去 Unpaywall/出版社 |
| 4 | 出版社 ScienceDirect | https://www.sciencedirect.com/science/article/abs/pii/S136192092500183X | **HTTP 403** | 反爬/订阅墙；返回页面为 TDM 提示页，无正文 |
| 5 | BIT 机构库 Pure | https://pure.bit.edu.cn/en/publications/joint-operation-strategy-of-parking-and-charging-infrastructure/ | HTTP 200 | 有题录、作者单位、引用数与**摘要**；页面未见可下载 OA 文件（无 Files 链接） |
| 6 | TRID（TRB） | https://trid.trb.org/View/2543833 | HTTP 200 | 有摘要；Availability: "Find a library where document is available"（无全文） |
| 7 | HSE 机构库（Pavlov） | https://publications.hse.ru/en/articles/1080480584 | 失败 | 工具报错 `unsupported content type "unknown"`，未取到内容；不据此声称不存在 |
| 8 | 检索（2 条查询） | web_search："Joint operation strategy..." repository pdf / 作者+机构 | 返回 8 条 | 命中上述机构库与 NSTL 题录，无 OA 全文链接 |

## 已获得的摘要（TRID 版，逐字摘录；BIT Pure 版同义）

> Charging pile sharing transforms the structure of the supply chain and influences the production decisions of parking space operators. The authors develop three strategies to study parking space operators' pile-building strategies using game theory: (1) commissioning a third-party company to build piles (Strategy P), (2) self-constructing charging piles (Strategy D), and (3) co-building and sharing charging piles with other operators (Strategy C). The results show that brand advantage has a negative effect on the low-brand operator in Strategies P and D but promotes revenue in Strategy C. … the higher the brand advantage (or brand spillover) … the smaller the fixed payment for the low-brand operator. Furthermore, operator L always has the lowest revenue in Strategy P. Finally, considering the maximization of social welfare, the government should provide parking space operator with a subsidy for building piles. These findings offer policy recommendations …

## 对写作的约束

- 只能按**摘要级**引用 N1/M18：可引“三种建桩策略 P/D/C、供应链共享改变结构、品牌优势与补贴建议”（确定，摘要原文可查）；**不可**推断其模型、约束、参数、定理或数值（UNVERIFIED）。
- 与 M06/M07 的逐项对照中，N1 列凡涉及模型细节必须标 UNVERIFIED，或者只填摘要直接支持的信息。
- 若必须引用 N1 的模型细节，需作者版或订阅访问；本轮无该权限，已在此登记。

## 未验证

- N1 是否在作者个人主页/会议版/预印本有合法开放副本：未穷尽检索（只检了 web 与两个机构库入口），标 UNVERIFIED。
- HSE 机构库页面内容：因工具不支持该内容类型未取到，UNVERIFIED。
