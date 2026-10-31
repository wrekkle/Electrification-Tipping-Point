# research/cost_model_20261030

成本模型 v2（口径见 docs/methods/COST-MODEL-V2.md）的参数来源核查工作目录。
2026-10-30 由 param-sources（task-4）建立。

| 文件/目录 | 是什么 |
|---|---|
| `parameters.json` | **交付物**：每项参数的数值或 null、单位、地区、年份、source_url、page_or_table、换算、status |
| `notes/` | Shoup(2007 ACCESS 版)、Biswas et al.(2016) 的选读笔记（页码证据） |
| `downloads/` | 本次实际下载的 PDF 与渲染页（含 SHA-256 记录，见报告第 5 节） |
| `extract_probe.py` / `inspect_pdf.py` / `dump_pages.py` / `render_pages.py` | 复现用工具：PDF 页数/SHA-256/关键词页、整页文字、扫描页转 PNG |
| `../docs/reports/2026-10-30-成本参数来源核查.md` | 人读报告与缺失清单 |

注意：`downloads/` 里的 Shoup/Biswas PDF **尚未**登记进 `literature/index.json`
（需要编号与索引配置改动，超出本任务写范围），报告第 5 节写了登记所需步骤。
