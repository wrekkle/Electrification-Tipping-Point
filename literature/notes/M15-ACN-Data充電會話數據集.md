# M15 ACN-Data 工作場所充電會話開放數據集

类型: 阅读笔记
状态: 草案
负责人: ev-data
日期: 2026-10-31
文献: M15
版本: ACN-Data（Caltech Adaptive Charging Network）；論文 "ACN-Data: Analysis and Applications of an Open EV Charging Dataset"；DOI/出版年未核（UNVERIFIED）
读的范围: 只核到 `https://ev.caltech.edu/research` 研究頁與資料集說明；論文記錄頁 `https://authors.caltech.edu/96442/` 本輪 SSL 失敗；未下載數據、未讀論文全文
本地文件: `research/official_data_20261031/ev_behavior/raw/ACN_research.html`（25,335 bytes，sha256 见 manifest）
下载端点: `https://ev.caltech.edu/research`（請求日誌 seq 22）

## 問題與方法

Caltech 的 Adaptive Charging Network（ACN）公開數據集：工作場所 EV 充電會話的動態數據，含到場/離場、能量、預估充電時長等；配套 ACN-Sim 模擬器與 ACN-Live 框架。研究頁描述其可用於自適應充電、太陽能消納與工作場所充電研究。

## 分母與可用範圍

- 觀測單位是「充電會話」（charging session），只有插槍充電的車輛才有記錄；沒有「未充電的 EV 停車事件」分母。
- 因此不能估 q_use（無法知道有多少 EV 到訪而未充電）、更不能估 q_need。
- 可估：連接時長、充電時長、能量需求、到達/離開時刻分佈、單樁利用率、排隊/延遲充電行為；若數據含離場時間，可近似「充電完成後仍連接」的滯留（但取決於會話結束定義）。
- 限制：工作場所單一場景、單一充電網絡、加州；參與者可能非隨機；無停車場全部到訪與車型/油車資訊。

## 本項目關係

- 作獨立樣本（非 M08/M09/M10/M12/M13 數據集）納入「充電會話數據」類，用於 device_time_utilization 與能量/時長分佈的方法參考，不用於 q 的核心估計。
- 本輪未下載原始數據、未核論文方法細節，狀態標 UNVERIFIED：僅文檔頁確認資料集存在與型態。
