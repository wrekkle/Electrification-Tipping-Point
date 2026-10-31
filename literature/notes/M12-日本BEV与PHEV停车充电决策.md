# M12 日本BEV与PHEV停车充电决策

类型: 阅读笔记
状态: 草案
负责人: tho25
日期: 2026-10-30
文献: M12
版本: Transportation Research Part D 150 (January 2026), 105094
读的范围: 出版商全文索引的数据、模型、附录B/C选读；无本地PDF，未通读/复现，登记摘要级。

Watanabe, A., Hidaka, K., Nishi, T., Sasai, T., & Fukushima, S. Charging behavior differences between BEVs and PHEVs: Evidence from vehicle log data. [DOI](https://doi.org/10.1016/j.trd.2025.105094)；[出版商全文](https://www.sciencedirect.com/science/article/pii/S1361920925005048)。

## 问题、方法与可复用点

2023年3–12月日本车辆日志，清洗后131辆BEV、953辆PHEV、约67万行程；混合logit刻画旅程结束后充电决策。区分家庭/公共/其他地点、SOC、停留至下次出行的时间和家庭充电条件。

## 局限、使用边界及本项目关系

3.1节明确仅行驶时有CAN数据，充电并非直接计量，而由前后状态变化推断，充电功率/插头未知。附录C又限定于“潜在可充电行程”，不等于所有进场EV。没有核完3.2筛选与标签阈值前，不迁移附录曲线的数值。

不能用附录B四舍五入后的“平均充电次数/平均行程数”冒充公共停车场概率；约63%的变化是安装家充的政策模拟效果，不是公共充电发生率。后端应允许BEV/PHEV与家庭充电条件分层，并把真实不可见SOC留在仿真内部，不给准入策略读取。证据位置：3.1–3.2、4.1、附录B表B.1与附录C；PDF页码未核。任务认 docs/TODO.md 的T23。
