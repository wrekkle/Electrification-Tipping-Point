# Biswas, Gopalakrishnan, Dutta, "Managing Overstaying Electric Vehicles in Park-and-Charge Facilities"

状态: 草案
文献编号: P37（2026-10-30 由 paper-lit 按 literature/README.md 正式登记；索引由脚本生成，见 literature/index.json）
版本: arXiv:1604.05471v2 作者稿（15 页），会议版为 IJCAI-16
读的范围: 第 1 页摘要、第 3 页风险/收费定义选段、第 7 页数值示例、第 11 页仿真参数

## 问题与方法
充完电不挪车（overstaying）是充电位利用率低的主因；用「超时罚金率 αo」管理，
把用户停车时长不确定性下的可接受性（罚金不超过 Cmax 的概率）与排队动态耦合，
求利用率与收入视角下的最优 αo。

## 读到的数（均为仿真假设，不是实测市场价）
- p.7 例：N=10 车位，λ=8 EV/h，μc=60/h（？原文例中列出 45/h、105/h 等），Cmax=$4，
  αc=$2/h → αo=$2.37/h 使利用率最大（30%）；从收入看 αo=$3.07/h 最优。
  （对照：无罚金时利用率 42%。）
- p.11：停车时长 Ta ~ U(30, 180) 分钟；Cmax 取 $4/$8/$10/$20，概率 0.4/0.3/0.2/0.1；
  充电费率 αc=$2/h。

## 可复用点
- 「充完滞留」应作为独立成本/资源阻塞机制建模，而不是并入普通停车失败。
- 罚金是转移支付，不是社会成本（与 COST-MODEL §6 一致）；真正社会成本要靠资源阻塞造成的
  后续车辆等待/绕行损失，用配对反事实估计。

## 局限与风险
- 印度研究情境的仿真参数，USD，且 αo 是机制参数不是损失单价。
- 不得把 $2.37/h 当成台北「占桩罚金」或「挪车代价」的参数值。

## 与本项目的关系
COST-MODEL-V2 §5 占桩影响归因分类（overstay_after_complete）的机制依据；
解释为什么不能用固定罚金代替反事实成本差。

## 证据位置
- p.7 "when we set N = 10 slots, λ = 8 EVs per hour ... Cmax = $4, αc = $2 per hour,
  we find that setting the penalty rate αo = $2.37 per hour provides the maximum value of
  utilization (30%)"
- p.11 "uniform distribution between 30 minutes and 180 minutes for Ta" ...
  "$4, $8, $10, $20 with probabilities 0.4, 0.3, 0.2, 0.1" ... "rate αc = $2 per hour"
- 本地文件（登记后已移入既定 PDF 目录）: research/ev_parking_math_20261029/PDFs/P37_Biswas_Managing_Overstaying_EVs_in_Park_and_Charge_Facilities_arXiv_1604.05471v2.pdf
  SHA-256 d56d1a290ee056afa0d80d462b02ded70a025c5b2096402c4b0890c8f36a8dfa，15 页
