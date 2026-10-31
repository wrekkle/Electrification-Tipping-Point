# -*- coding: utf-8 -*-
"""Cost model: manuscript equations (2)-(7), with explicit accounting switches.

Period convention
-----------------
All costs are expressed over H years (run.horizon_years):

    K_H(m)   = m * (C_char / L + C_om_year) * H          [RMB]  (eq. 2)
    C_loss_H = H * D_year * E[daily leaving loss]        [RMB]  (eq. 3/4)
    C_com_H  = H * D_year * E[N_l * R_com * C_com]       [RMB]  (eq. 7, separate)

where D_year is run.operating_days_per_year.  Straight-line amortisation is
used (the manuscript states a 5-year life but eq. (2) omits the conversion;
the switch exposes that difference, see report T4-2).

Complaint accounting
--------------------
embedded follows eq. (3)/(4) literally: every leaving event carries C_com as
if each leaver complained.
separate removes C_com from the event and adds eq. (7) once, weighted by the
expected complaint probability over the value-of-time distribution.
"""
from __future__ import annotations

import math

import numpy as np


def expected_vot(mu, sigma):
    """Mean of lognormal(mu, sigma)."""
    return math.exp(mu + 0.5 * sigma * sigma)


def sample_vot(mu, sigma, n=200000, seed=12345):
    """Deterministic sample of the VOT distribution (independent RNG stream)."""
    rng = np.random.default_rng(seed)
    return rng.lognormal(mean=mu, sigma=sigma, size=n)


def complaint_probability(vot, a, b):
    """Logit complaint probability as a function of value of time."""
    z = np.asarray(vot, dtype=float) * b + a
    z = np.clip(z, -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-z))


class CostModel:
    """RMB cost objects derived from one config."""

    def __init__(self, cfg, seed=12345):
        c = cfg["cost"]
        self.c_char = float(c["c_char"])
        self.pile_life = float(c["pile_life_years"])
        self.c_om_year = float(c["c_om_year"])
        self.h_years = float(cfg["run"]["horizon_years"])
        self.days_per_year = float(cfg["run"]["operating_days_per_year"])
        self.c_en = {"ev": float(c["c_en_ev"]), "icev": float(c["c_en_icev"])}
        self.t_hunt_h = float(c["t_hunt_min"]) / 60.0
        self.k_delay = float(c["k_delay"])
        self.v_kmh = float(c["v_kmh"])
        self.c_fu = {"ev": float(c["c_fu_ev"]), "icev": float(c["c_fu_icev"])}
        self.vot_mu = float(c["vot_mu"])
        self.vot_sigma = float(c["vot_sigma"])
        self.c_com = float(c["c_com"])
        self.logit_a = float(c["complaint_logit_a"])
        self.logit_b = float(c["complaint_logit_b"])
        self.accounting = str(c["complaint_accounting"]).strip().lower()
        if self.accounting not in ("embedded", "separate"):
            raise ValueError("complaint_accounting must be embedded|separate")
        self.event_cost_scale = float(c["event_cost_scale"])
        self.complaint_scale = float(c.get("c_com_scale", 1.0))
        self.vot_scale = float(c.get("vot_scale", 1.0))
        self.vot_sigma_scale = float(c.get("vot_sigma_scale", 1.0))

        self.mean_vot = expected_vot(self.vot_mu, self.vot_sigma) * self.vot_scale
        self._vot_draws = sample_vot(
            self.vot_mu, self.vot_sigma * self.vot_sigma_scale, seed=seed
        ) * self.vot_scale
        self.mean_complaint_prob = float(
            complaint_probability(self._vot_draws, self.logit_a, self.logit_b).mean()
        )

    # -- per-event components (RMB per leaving vehicle) --------------------
    def time_cost(self):
        """Eq. (5): T_hunt * k * C_vot, T_hunt in hours."""
        return self.t_hunt_h * self.k_delay * self.mean_vot

    def fuel_cost(self, vehicle):
        """Eq. (6): T_hunt * v * C_fu."""
        return self.t_hunt_h * self.v_kmh * self.c_fu[vehicle]

    def event_cost(self, vehicle, embedded=None):
        """Per-leaving-event social loss (before the global event scale)."""
        embedded = (self.accounting == "embedded") if embedded is None else embedded
        base = self.c_en[vehicle] + self.time_cost() + self.fuel_cost(vehicle)
        if embedded:
            base += self.c_com * self.complaint_scale
        else:
            base += self.mean_complaint_prob * self.c_com * self.complaint_scale
        return base * self.event_cost_scale

    def event_components(self, vehicle):
        return {
            "c_en": self.c_en[vehicle],
            "c_time": self.time_cost(),
            "c_fuel": self.fuel_cost(vehicle),
            "c_com_embedded": self.c_com * self.complaint_scale,
            "c_com_expected": self.mean_complaint_prob * self.c_com * self.complaint_scale,
            "event_cost": self.event_cost(vehicle),
        }

    # -- aggregate costs ----------------------------------------------------
    def pile_annual_cost(self):
        return self.c_char / self.pile_life + self.c_om_year

    def pile_cost(self, m):
        """K_H(m): capital (straight line) plus O&M over H years."""
        return float(m) * self.pile_annual_cost() * self.h_years

    def loss_cost(self, daily_ev_leavers, daily_icev_leavers):
        """H-period leaving loss for per-day counts (mean over scenarios)."""
        per_day = (
            np.asarray(daily_ev_leavers, dtype=float) * self.event_cost("ev")
            + np.asarray(daily_icev_leavers, dtype=float) * self.event_cost("icev")
        )
        return float(np.mean(per_day)) * self.days_per_year * self.h_years

    def separate_complaint_cost(self, daily_total_leavers):
        """Eq. (7) as a separate, non-duplicated complaint budget."""
        per_day = np.asarray(daily_total_leavers, dtype=float) * (
            self.mean_complaint_prob * self.c_com * self.complaint_scale
        )
        return float(np.mean(per_day)) * self.days_per_year * self.h_years

    def psc(self, m, daily_ev_leavers, daily_icev_leavers):
        total = self.pile_cost(m) + self.loss_cost(daily_ev_leavers, daily_icev_leavers)
        if self.accounting == "separate":
            total += self.separate_complaint_cost(
                np.asarray(daily_ev_leavers, dtype=float)
                + np.asarray(daily_icev_leavers, dtype=float)
            )
        return float(total)

    def daily_loss(self, ev_leavers, icev_leavers):
        """Per-day loss over the H-year horizon, kept scenario by scenario."""
        return (
            np.asarray(ev_leavers, dtype=float) * self.event_cost("ev")
            + np.asarray(icev_leavers, dtype=float) * self.event_cost("icev")
        ) * (self.days_per_year * self.h_years)

    def daily_total_loss(self, ev_leavers, icev_leavers):
        """daily_loss plus the separate complaint budget when accounting=separate."""
        total = self.daily_loss(ev_leavers, icev_leavers)
        if self.accounting == "separate":
            total = total + (
                np.asarray(ev_leavers, dtype=float)
                + np.asarray(icev_leavers, dtype=float)
            ) * (self.mean_complaint_prob * self.c_com * self.complaint_scale) * (
                self.days_per_year * self.h_years)
        return total
