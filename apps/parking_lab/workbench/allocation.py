"""连接器负载、Erlang-B 阻塞与整数容量评价（纯标准库，可手算复核）。

占位口径（第二轮 R2-D6）：
- occupancy_model="dwell"（默认）：连接器从 EV 入场到离场一直被占用，包括本次不充电的
  EV 与充完仍滞留的 EV；故 mean_connector_minutes = mean_dwell_min，
  offered_load_erlang = lambda_ev_hour*mean_dwell_min/60。
- occupancy_model="charge" 为 legacy 对照口径（旧公式
  q_need*mean_charge_min+(1-q_need)*mean_dwell_min），假设"充完立即释放枪"；该假设与
  "充满不释放枪"的实际规则不一致、会系统性低估占位负荷，结果标 legacy=True 仅作历史对照。
- arrival_rate_hour 为每小时到达车辆数；ev_share 为电动车比例，q_need 为其中真正需要充电
  的比例；lambda_ev_hour = arrival_rate_hour*ev_share，
  lambda_charge_hour = lambda_ev_hour*q_need。

Erlang-B 递推：B(0)=1，B(n)=a*B(n-1)/(n+a*B(n-1))；a=0 时 B(0)=1、B(n>=1)=0。
解析近似的适用条件（不是仿真事实）：到达为平稳 Poisson 过程、服务时长独立同分布、
连接器同质且可数、无排队（全忙到达立即离开/不等待）、系统处于稳态、
负荷 a = 到达率×平均占位时长（Erlang）。erlang_b_closed_form 用独立闭式求和交叉校验。

服务水平整数规则 service_level_k / budgeted_service_search 返回状态字典
{status, k, alpha, evaluated_max, baseline, note, boundary, bound_kind}；status ∈ achieved /
no_demand / budget_exhausted / infeasible_upper_bound / missing_data；bound_kind ∈ achieved /
user_bound / engineering_bound / budget_exhausted / no_demand / missing_data。
search_max 为用户/搜索上限（缺省时以已评估最大 k 为工程/枚举上限），budget_max 为评估预算；
无 k 达标时不得用 max(by_k) 冒充推荐；缺参/缺行一律 None。min_servers_for_blocking 在零负荷
返回 0（零需求不推荐 1 台）。integer_recommendation 把逐种子整数 k 汇总为可安装推荐：
任一种子为 None 只给"cap+X 下界"，非整数中位数标 statistical_summary_not_installable。

costs 以连接器数 k（int >= 0）为键、社会成本为值，None 表示该 k 不可评价；
派生量遇到 None 一律返回 None，禁止填 0 或插值猜测；deltas 仅在 k 与 k+1 均可评价时定义。
连续解取整候选集为 {floor(x), floor(x+0.5), ceil(x)} 去重升序，显式避开银行家舍入。
"""
from __future__ import annotations

import math

_TOL = 1e-12

SERVICE_LEVEL_KEY = "unmet_no_connector_events"
SERVICE_LEVEL_STATUSES = (
    "achieved", "no_demand", "budget_exhausted", "infeasible_upper_bound", "missing_data",
)
BOUND_KINDS = (
    "achieved", "user_bound", "engineering_bound", "budget_exhausted", "no_demand", "missing_data",
)
INTEGER_RECOMMENDATION_STATUSES = (
    "ok", "statistical_summary_not_installable", "lower_bound", "missing_data",
)


def _finite(name, value):
    """把 value 转为有限浮点数，否则 ValueError。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 必须是数值，收到 {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} 必须有限，收到 {value!r}")
    return number


def _non_negative(name, value):
    number = _finite(name, value)
    if number < 0.0:
        raise ValueError(f"{name} 必须非负，收到 {value!r}")
    return number


def _fraction(name, value):
    number = _finite(name, value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} 必须在 [0, 1] 内，收到 {value!r}")
    return number


def _integer(name, value, minimum):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} 必须是整数，收到 {value!r}")
    if value < minimum:
        raise ValueError(f"{name} 必须 >= {minimum}，收到 {value!r}")
    return int(value)


def _non_decreasing(previous, current):
    """允许 _TOL 量级浮点误差的"不降"判定。"""
    return current + _TOL * max(1.0, abs(previous), abs(current)) >= previous


def mean_connector_load(arrival_rate_hour, ev_share, q_need, mean_charge_min,
                      mean_dwell_min, *, occupancy_model="dwell"):
    """把到达率与占位时长折算成连接器平均负载（小时口径）。

    默认 occupancy_model="dwell"：连接器占位 = 全部 EV 的停留时长（含本次不充电的 EV 与
    充完仍滞留的 EV，即"充满不释放枪"），mean_connector_minutes = mean_dwell_min。
    occupancy_model="charge" 是 legacy 对照口径（旧公式
    q_need*mean_charge_min+(1-q_need)*mean_dwell_min），假设充完立即释放枪；与实际规则不一致、
    系统性低估占位负荷，返回 legacy=True 仅作历史对照。
    返回 lambda_ev_hour、lambda_charge_hour、mean_connector_minutes、offered_load_erlang、
    occupancy_model、legacy；lambda_ev_hour=arrival_rate_hour*ev_share，
    lambda_charge_hour=lambda_ev_hour*q_need，
    offered_load_erlang=lambda_ev_hour*mean_connector_minutes/60。
    任一参数非有限或为负、ev_share/q_need 不在 [0,1]、occupancy_model 非法抛 ValueError。
    """
    arrival = _non_negative("arrival_rate_hour", arrival_rate_hour)
    ev_share_value = _fraction("ev_share", ev_share)
    need_share = _fraction("q_need", q_need)
    charge_min = _non_negative("mean_charge_min", mean_charge_min)
    dwell_min = _non_negative("mean_dwell_min", mean_dwell_min)
    if occupancy_model not in ("dwell", "charge"):
        raise ValueError(f"occupancy_model 必须是 'dwell' 或 'charge'，收到 {occupancy_model!r}")
    lambda_ev_hour = arrival * ev_share_value
    lambda_charge_hour = lambda_ev_hour * need_share
    if occupancy_model == "dwell":
        mean_connector_minutes = dwell_min
    else:
        mean_connector_minutes = need_share * charge_min + (1.0 - need_share) * dwell_min
    return {
        "lambda_ev_hour": lambda_ev_hour,
        "lambda_charge_hour": lambda_charge_hour,
        "mean_connector_minutes": mean_connector_minutes,
        "offered_load_erlang": lambda_ev_hour * mean_connector_minutes / 60.0,
        "occupancy_model": occupancy_model,
        "legacy": occupancy_model == "charge",
    }


def erlang_b(offered_load, servers):
    """Erlang-B 阻塞概率（全忙概率），递推 B(0)=1、B(n)=a*B(n-1)/(n+a*B(n-1))。

    offered_load 为 a（Erlang）且须有限非负；servers 须为 >=1 整数；非法输入抛 ValueError。
    B(0)=1 指没有连接器时全部到达被阻塞，本函数只对 servers>=1 求值。
    """
    load = _non_negative("offered_load", offered_load)
    count = _integer("servers", servers, 1)
    block = 1.0
    for index in range(1, count + 1):
        block = (load * block) / (index + load * block)
    return block


def erlang_b_closed_form(offered_load, servers):
    """Erlang-B 的独立闭式求和参考实现（log 空间），仅作交叉校验，不用于生产路径。

    闭式 B(a,c) = (a^c/c!) / sum_{n=0}^{c} a^n/n!；a 须有限非负、c 须 >=1 整数；
    a=0 时返回 0.0（与 erlang_b 的 a=0 约定一致）。实现用 lgamma 求 log(n!) 并在 log 空间
    归一化，与 erlang_b 的递推是两条独立算式，用于测试/文档核对；非法输入抛 ValueError。
    """
    load = _non_negative("offered_load", offered_load)
    count = _integer("servers", servers, 1)
    if load == 0.0:
        return 0.0
    log_load = math.log(load)
    log_terms = [n * log_load - math.lgamma(n + 1) for n in range(count + 1)]
    top = max(log_terms)
    total = math.fsum(math.exp(term - top) for term in log_terms)
    return math.exp(log_terms[-1] - top) / total


def min_servers_for_blocking(offered_load, target_blocking, k_max):
    """最小的 servers 使 erlang_b(offered_load, servers) <= target_blocking。
    target_blocking 须在 (0,1) 开区间；k_max 为允许检验的最大连接器数（>=1）。
    load=0（零需求）返回 0，不推荐 1 台；1..k_max 内达不到目标返回 None。非法输入抛 ValueError。
    """
    load = _non_negative("offered_load", offered_load)
    target = _finite("target_blocking", target_blocking)
    if not 0.0 < target < 1.0:
        raise ValueError(f"target_blocking 必须在 (0, 1) 内，收到 {target_blocking!r}")
    limit = _integer("k_max", k_max, 1)
    if load == 0.0:
        return 0
    for count in range(1, limit + 1):
        if erlang_b(load, count) <= target:
            return count
    return None


def _service_metric(row, key, label):
    """从 by_k 的一行取服务指标；行/值为 None 或缺键返回 None，非法值抛 ValueError。"""
    if row is None:
        return None
    if isinstance(row, dict):
        if key not in row:
            return None
        value = row[key]
    elif isinstance(row, bool) or not isinstance(row, (int, float)):
        raise ValueError(f"{label} 必须是记录（dict）、数值或 None，收到 {row!r}")
    else:
        value = row
    if value is None:
        return None
    return _non_negative(f"{label}[{key!r}]", value)


def _service_values(by_k, key):
    """把 by_k 规整为 {int k: float|None}；by_k 须为 {int: 记录 dict|数值} 字典。"""
    if not isinstance(key, str) or not key:
        raise ValueError(f"key 必须是非空字符串，收到 {key!r}")
    if not isinstance(by_k, dict):
        raise ValueError(f"by_k 必须是 {{int: 记录|数值}} 字典，收到 {type(by_k).__name__}")
    values = {}
    for raw_k, row in by_k.items():
        count = _integer("by_k 的键", raw_k, 0)
        values[count] = _service_metric(row, key, f"by_k[{count}]")
    return values


def _service_result(status, *, alpha, evaluated_max, baseline, k=None, note,
                    boundary=False, bound_kind):
    """组装服务水平状态字典（内部；对外键固定为 status/k/alpha/evaluated_max/baseline/note/boundary/bound_kind）。"""
    if status not in SERVICE_LEVEL_STATUSES:
        raise ValueError(f"未知服务水平状态 {status!r}")
    if bound_kind not in BOUND_KINDS:
        raise ValueError(f"未知边界类型 {bound_kind!r}")
    return {"status": status, "k": k, "alpha": alpha, "evaluated_max": evaluated_max,
            "baseline": baseline, "note": note, "boundary": boundary, "bound_kind": bound_kind}


def _service_level_search(values, alpha, search_max, budget_max):
    """在 {int k: float|None} 上做整数服务水平搜索，返回状态字典（内部实现）。

    k_alpha = min{k>=1 : U(k) <= alpha*U(0)}。位置参数是已绑定的搜索上限与评估预算：
    - search_max: 用户/搜索上限；None 时以 by_k 已评估最大 k 为工程/枚举上限；
    - budget_max: 评估预算（本次最多评估到 k=budget_max）；None 时无额外预算限制。
    缺 k=0 -> missing_data；U(0)=0 -> no_demand（k=0）；缺中间行 -> missing_data；
    无 k 达标时：已检查到 search_max -> infeasible_upper_bound，bound_kind 区分 user_bound
    （显式 search_max）与 engineering_bound（缺省 by_k 上限）；预算/数据只到更小的 k ->
    budget_exhausted（k=None，evaluated_max 为实际检查到的最大 k）。恰在 search_max 达标 ->
    achieved 且 boundary=True。
    """
    alpha_value = _finite("alpha", alpha)
    if not 0.0 < alpha_value <= 1.0:
        raise ValueError(f"alpha 必须在 (0, 1] 内，收到 {alpha!r}")
    data_max = max(values) if values else None
    search_bound = None if search_max is None else _integer("search_max", search_max, 0)
    budget = None if budget_max is None else _integer("budget_max", budget_max, 0)
    limits = [bound for bound in (data_max, search_bound, budget) if bound is not None]
    evaluated_max = min(limits) if limits and data_max is not None else None
    if 0 not in values or values[0] is None:
        return _service_result("missing_data", alpha=alpha_value, evaluated_max=evaluated_max,
                               baseline=None, k=None, bound_kind="missing_data",
                               note="缺 k=0 基线行或基线值缺失，无法定义服务水平")
    baseline = values[0]
    if baseline == 0.0:
        return _service_result("no_demand", alpha=alpha_value, evaluated_max=evaluated_max,
                               baseline=baseline, k=0, bound_kind="no_demand",
                               note="U(0)=0：无连接器时也没有未服务需求，k=0 即达标")
    target_bound = search_bound if search_bound is not None else data_max
    threshold = alpha_value * baseline
    tolerance = _TOL * max(1.0, abs(threshold))
    for count in range(1, evaluated_max + 1):
        if count not in values or values[count] is None:
            return _service_result("missing_data", alpha=alpha_value, evaluated_max=evaluated_max,
                                   baseline=baseline, k=None, bound_kind="missing_data",
                                   note=f"缺行 k={count}：k=1..{evaluated_max} 必须连续可评价才能给出整数推荐")
        value = values[count]
        if value <= threshold + tolerance:
            boundary = count == target_bound
            note = f"k={count} 使 U(k)={value:.6g} <= alpha*U(0)={threshold:.6g}"
            if boundary:
                note += f"；恰在搜索上限 k={target_bound} 达标（boundary=True），未再扩大搜索"
            return _service_result("achieved", alpha=alpha_value, evaluated_max=evaluated_max,
                                   baseline=baseline, k=count, note=note,
                                   boundary=boundary, bound_kind="achieved")
    if evaluated_max is not None and target_bound is not None and evaluated_max >= target_bound:
        bound_kind = "user_bound" if search_bound is not None else "engineering_bound"
        source = "用户给定" if bound_kind == "user_bound" else "数据/工程"
        return _service_result("infeasible_upper_bound", alpha=alpha_value,
                               evaluated_max=evaluated_max, baseline=baseline, k=None,
                               bound_kind=bound_kind,
                               note=f"无 k 达标且已检查到{source}上限 k={target_bound}；"
                                    f"k=None，不得用 max(by_k) 冒充推荐")
    return _service_result("budget_exhausted", alpha=alpha_value, evaluated_max=evaluated_max,
                           baseline=baseline, k=None, bound_kind="budget_exhausted",
                           note=f"无 k 达标但只评估到 k={evaluated_max}（搜索上限 k={target_bound} 未到）；"
                                f"k=None，需扩大预算")


def service_level_k(by_k, alpha, *, key=SERVICE_LEVEL_KEY, search_max=None,
                    budget_max=None, k_hard_max=None, metric=None):
    """整数服务水平规则 k_alpha = min{k>=1 : U(k) <= alpha*U(0)} 的状态化实现（R2-D5 / R3-B）。

    by_k 为 {int k>=0: 记录 dict 或数值}：记录取 by_k[k][key]（默认 "unmet_no_connector_events"），
    数值简写表示该 k 的服务指标本身；metric= 是 key= 的旧别名（第二轮 rules_v2 harness 使用）。
    alpha 须在 (0,1]。搜索边界（默认参数保持第二轮行为）：
    - search_max: 用户给定的搜索上限（允许推荐的最大 k）；None 表示"by_k 已评估到的最大 k
      即工程/枚举上限"。
    - budget_max: 评估预算，本次最多评估到 k=budget_max；超出预算的 by_k 行视为未评估。
    - k_hard_max: 第二轮旧参数别名，等价 search_max（同时给且不同 -> ValueError）。
    状态与 bound_kind：达标 -> achieved（bound_kind="achieved"；k 恰在搜索上限时 boundary=True）；
    U(0)=0 -> no_demand（k=0，bound_kind="no_demand"）；缺 k=0/缺中间行 -> missing_data（k=None）；
    无 k 达标且已检查到搜索上限 -> infeasible_upper_bound（bound_kind="user_bound"；未给
    search_max、以 by_k 上限为界时 bound_kind="engineering_bound"）；预算/数据只到更小的 k ->
    budget_exhausted（k=None，附 evaluated_max，bound_kind="budget_exhausted"）。返回
    {"status","k","alpha","evaluated_max","baseline","note","boundary","bound_kind"}；
    缺失一律 None，不填 0、不插值。非法输入（指标非有限负数、键非 int、alpha/边界/预算非法）抛 ValueError。
    """
    if metric is not None:
        if not isinstance(metric, str) or not metric:
            raise ValueError(f"metric 必须是非空字符串，收到 {metric!r}")
        if key != SERVICE_LEVEL_KEY and key != metric:
            raise ValueError("key 与 metric 同时给出但取值不同")
        key = metric
    if k_hard_max is not None:
        legacy = _integer("k_hard_max", k_hard_max, 0)
        if search_max is not None and _integer("search_max", search_max, 0) != legacy:
            raise ValueError("search_max 与 k_hard_max 同时给出但取值不同")
        search_max = legacy
    values = _service_values(by_k, key)
    return _service_level_search(values, alpha, search_max, budget_max)


def _service_evaluator_value(evaluate, count):
    """调用 evaluate(k) 并把返回值规整为 float|None；记录取默认服务键。"""
    value = evaluate(count)
    if isinstance(value, dict):
        value = value.get(SERVICE_LEVEL_KEY)
    if value is None:
        return None
    return _non_negative(f"evaluate({count})", value)


def budgeted_service_search(evaluate, alpha, k_initial_max, k_hard_max=None, *,
                            search_max=None, budget_max=None):
    """分批扩展的整数服务水平搜索：先评估 k=0..k_initial_max，未达标再按上限翻倍扩展。

    evaluate(k) 返回该 k 的服务指标数值（或含默认键的记录）或 None（不可评价）；
    alpha 须在 (0,1]。search_max 为搜索上限，也可用第二轮旧位置参数 k_hard_max 给出
    （同时给且不同 -> ValueError；两者都缺 -> ValueError）；budget_max 为评估预算上限
    （None 表示一直扩展到 search_max）。要求 1 <= k_initial_max <= search_max；
    初始批大于 budget_max 时截断到预算。达到目标/无需求/缺行即停，否则批次上限翻倍
    （至少 +1、不超过 min(search_max, budget_max)）。耗尽时返回状态而非伪 k：
    - 扩展到 search_max 仍无 k 达标 -> infeasible_upper_bound、k=None、bound_kind="user_bound"；
    - 预算先耗尽 -> budget_exhausted、k=None、附 evaluated_max。
    恰在 search_max 达标 -> boundary=True；None 行按缺行处理 -> missing_data。
    返回与 service_level_k 相同的状态字典。非法输入抛 ValueError。
    """
    if not callable(evaluate):
        raise ValueError(f"evaluate 必须可调用，收到 {evaluate!r}")
    initial = _integer("k_initial_max", k_initial_max, 1)
    if k_hard_max is not None:
        legacy = _integer("k_hard_max", k_hard_max, 1)
        if search_max is not None and _integer("search_max", search_max, 1) != legacy:
            raise ValueError("search_max 与 k_hard_max 同时给出但取值不同")
        search_max = legacy
    if search_max is None:
        raise ValueError("必须给出 search_max（或旧参数 k_hard_max）作为搜索上限")
    target = _integer("search_max", search_max, 1)
    if initial > target:
        raise ValueError(f"k_initial_max（{initial}）必须 <= search_max（{target}）")
    budget = None if budget_max is None else _integer("budget_max", budget_max, 0)
    alpha_value = _finite("alpha", alpha)
    if not 0.0 < alpha_value <= 1.0:
        raise ValueError(f"alpha 必须在 (0, 1] 内，收到 {alpha!r}")
    cap = target if budget is None else min(target, budget)
    values = {}
    next_k = 0

    def extend(limit):
        nonlocal next_k
        while next_k <= limit:
            values[next_k] = _service_evaluator_value(evaluate, next_k)
            next_k += 1

    extend(min(initial, cap))
    while True:
        result = _service_level_search(values, alpha_value, target, budget)
        if result["status"] != "budget_exhausted":
            return result
        current = max(values)
        next_limit = min(cap, max(current + 1, 2 * current))
        if next_limit <= current:
            return result
        extend(next_limit)


def integer_recommendation(per_seed_k, cap):
    """把逐种子整数 k 汇总为可安装推荐（第三轮 R3-B）。

    per_seed_k 为每个随机种子一个整数 k 的序列（list/tuple）；元素 None 表示该种子在 cap 内
    没有达标的 k，只能给"≥ cap+1"的下界，不得当作可安装值。cap 为枚举/工程上限（int>=0）。
    median 为已知整数的中位数（偶数个取平均，可能非整数）；q90 取最近秩（升序第 ceil(0.9*n) 个）。
    recommended_k 必为 int（除 None 下界情形）：中位数为整数时取中位数，非整数时向上取整；
    任一种子为 None -> recommended_k=None、status="lower_bound"、note 写"cap+X 下界"；
    median 非整数 -> note 固定为 "statistical_summary_not_installable"（统计摘要，不是安装值）。
    返回 {"per_seed","median","q90","recommended_k","status","note"}；status ∈ ok /
    statistical_summary_not_installable / lower_bound / missing_data。非法输入抛 ValueError。
    """
    if not isinstance(per_seed_k, (list, tuple)):
        raise ValueError(f"per_seed_k 必须是 list/tuple，收到 {type(per_seed_k).__name__}")
    limit = _integer("cap", cap, 0)
    seeds = []
    for index, value in enumerate(per_seed_k):
        if value is None:
            seeds.append(None)
        elif isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"per_seed_k[{index}] 必须是 int 或 None，收到 {value!r}")
        elif value < 0:
            raise ValueError(f"per_seed_k[{index}] 必须非负，收到 {value!r}")
        else:
            seeds.append(int(value))
    if not seeds:
        return {"per_seed": [], "median": None, "q90": None, "recommended_k": None,
                "status": "missing_data", "note": "per_seed_k 为空：没有种子结果可汇总"}
    known = sorted(value for value in seeds if value is not None)
    missing = sum(1 for value in seeds if value is None)
    lower_note = (f"安装数是下界 ≥ {limit}+1 = {limit + 1}（cap+X 下界，cap={limit}，"
                  f"X≥1 未识别），不得当作可安装 k")
    if not known:
        return {"per_seed": seeds, "median": None, "q90": None, "recommended_k": None,
                "status": "lower_bound",
                "note": f"全部 {len(seeds)} 个种子在 cap={limit} 内无 k 达标：{lower_note}"}
    count = len(known)
    if count % 2:
        median = known[count // 2]
    else:
        low, high = known[count // 2 - 1], known[count // 2]
        median = low if low == high else (low + high) / 2.0
    rank = max(1, int(math.ceil(0.9 * count)))
    q90 = known[rank - 1]
    if missing:
        return {"per_seed": seeds, "median": median, "q90": q90, "recommended_k": None,
                "status": "lower_bound",
                "note": f"有 {missing} 个种子在 cap={limit} 内无 k 达标：{lower_note}"}
    if isinstance(median, float) and not median.is_integer():
        return {"per_seed": seeds, "median": median, "q90": q90,
                "recommended_k": int(math.ceil(median)),
                "status": "statistical_summary_not_installable",
                "note": "statistical_summary_not_installable"}
    return {"per_seed": seeds, "median": median, "q90": q90,
            "recommended_k": int(median), "status": "ok",
            "note": f"中位数 k={median}、q90={q90} 为整数，可直接作为安装数"}

def _normalise_costs(costs):
    """校验 costs 为 {int k>=0: 有限 float | None}，返回同构 dict。"""
    if not isinstance(costs, dict):
        raise ValueError(f"costs 必须是 {{int: float|None}} 字典，收到 {type(costs).__name__}")
    normalised = {}
    for key, value in costs.items():
        count = _integer(f"costs 的键", key, 0)
        normalised[count] = None if value is None else _finite(f"costs[{count}]", value)
    return normalised


def _cost_summary(costs):
    feasible = sorted(count for count, value in costs.items() if value is not None)
    if not feasible:
        return {"best_k": [], "best_cost": None, "deltas": {},
                "marginal_non_decreasing": None, "feasible_k": []}
    best_cost = min(costs[count] for count in feasible)
    best_k = [count for count in feasible if math.isclose(costs[count], best_cost, rel_tol=_TOL, abs_tol=_TOL)]
    deltas = {}
    for count in feasible:
        current, following = costs.get(count), costs.get(count + 1)
        if current is not None and following is not None:
            deltas[count] = following - current
    ordered = [deltas[count] for count in sorted(deltas)]
    marginal = None if len(ordered) < 2 else all(
        _non_decreasing(previous, current) for previous, current in zip(ordered, ordered[1:]))
    return {"best_k": best_k, "best_cost": best_cost, "deltas": deltas,
            "marginal_non_decreasing": marginal, "feasible_k": feasible}


def evaluate_integer_costs(costs):
    """评价整数连接器数方案：最优 k、并列、边际差与边际单调性。

    costs 为 {int k>=0: 有限 float 或 None}。返回 best_k（成本最小的全部 k，升序）、
    best_cost（无可行 k 时 None）、deltas{k: C(k+1)-C(k)}（k 与 k+1 均可评价才算）、
    marginal_non_decreasing（deltas 少于 2 个为 None，否则全部不降）、
    feasible_k（非 None 的 k 升序）。空输入/全 None 时 best_k=[]、best_cost=None；非法值抛 ValueError。
    """
    return _cost_summary(_normalise_costs(costs))


def rounding_candidates(k_cont):
    """连续解 k_cont 的整数候选：{floor, floor(x+0.5), ceil} 去重升序。

    floor(x+0.5) 即四舍五入（half-up），避免 Python round 的银行家舍入；k_cont 须有限非负。
    """
    continuous = _non_negative("k_cont", k_cont)
    return sorted({int(math.floor(continuous)), int(math.floor(continuous + 0.5)), int(math.ceil(continuous))})


def compare_rounding(costs, k_cont):
    """比较"连续解就近取整"与"整数全局最优"的差距。

    返回 k_cont、candidates{k: 成本或 None}（缺失/None 记 None）、best_among_candidates
    （候选内最优 k 的升序列表；均不可评价时为空）、global_best（evaluate_integer_costs 的
    best_k）与 selection_gap（候选内最优成本减全局最优成本，任一侧 None 则 None）。
    """
    normalised = _normalise_costs(costs)
    continuous = _non_negative("k_cont", k_cont)
    summary = _cost_summary(normalised)
    candidates = {count: normalised.get(count) for count in rounding_candidates(continuous)}
    priced = [(count, value) for count, value in candidates.items() if value is not None]
    if priced:
        best_among = min(value for _, value in priced)
        best_among_candidates = sorted(
            count for count, value in priced if math.isclose(value, best_among, rel_tol=_TOL, abs_tol=_TOL))
        global_cost = summary["best_cost"]
        selection_gap = None if global_cost is None else best_among - global_cost
    else:
        best_among_candidates, selection_gap = [], None
    return {"k_cont": continuous, "candidates": candidates,
            "best_among_candidates": best_among_candidates,
            "global_best": list(summary["best_k"]), "selection_gap": selection_gap}


def regret(costs, recommended_k):
    """推荐方案 k 相对整数全局最优的后悔值与后悔比。

    返回 recommended_k、cost（该 k 成本，缺失/None 记 None）、best_cost、regret=C(k)-min C
    与 regret_ratio=regret/best_cost（best_cost 为 None 或 <=0 时 None，避免除零与负基准）。
    """
    normalised = _normalise_costs(costs)
    key = _integer("recommended_k", recommended_k, 0)
    cost = normalised.get(key)
    best_cost = _cost_summary(normalised)["best_cost"]
    value = None if cost is None or best_cost is None else cost - best_cost
    ratio = None if value is None or best_cost is None or best_cost <= 0.0 else value / best_cost
    return {"recommended_k": key, "cost": cost, "best_cost": best_cost,
            "regret": value, "regret_ratio": ratio}
