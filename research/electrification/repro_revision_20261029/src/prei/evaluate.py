# -*- coding: utf-8 -*-
"""evaluate

Enumeration, scenario-by-candidate cost matrices and design evaluation.

Common random numbers: one set of daily scenarios is drawn per
(lot type, EV mode, r) and replayed for every candidate design and rule.
The reproduction unit is the day block (see run.block_days); hourly
correlation inside a day is represented by the NHPP in the v2 layer.

拆分后仅保留 facade；其余实现由下列模块提供并在此重新导出（公共导入面不变）。
"""
from __future__ import annotations
import copy
import numpy as np
from . import config, costs, demand, simulator, stats

from .evaluate_base import LOT_TYPES, STATIC_MODES, V2_METRIC_KEYS, arrivals_mean, v2_lot_arrival_scale, composition_of, m_candidates, integer_candidates, scenario_set, static_leavers, mode_pile_cost, static_matrices, curves_rows, optimum_rows, modes_summary, etp_rows, prepare_v2_day, v2_days, v2_designs, v2_pile_cost, design_label
from .evaluate_v2 import v2_cell_matrix, v2_rows, v2_eval, v2_best, _pick, decomposition_rows, cvar_fields, v2_cell_stats, refine_r_grid, v2_etp_points, _windows_to_text, v2_g_structure
from .evaluate_outputs import fig8_rows, feasibility_rows, saa_rows


