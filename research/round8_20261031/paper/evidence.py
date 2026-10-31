# -*- coding: utf-8 -*-
"""Number provenance for the rev5 build: every empirical number resolves to a
machine output under research/round8_20261031/experiments/.

The resolver is deliberately fail-loud: a number whose source file, row or
column is missing is reported as [UNRESOLVED:token] and listed in the build
manifest.  In strict (real) mode the build refuses to save if any token is
unresolved.  Nothing is ever filled from memory or from an older draft.
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
import statistics

SCHEMA = "round8/evidence/v1"
TOKEN = re.compile(r"\{\{([A-Za-z0-9_.]+)\}\}")


class MissingInput(Exception):
    pass


class Table:
    def __init__(self, relpath, path, rows):
        self.relpath = relpath
        self.path = path
        self.rows = rows
        self.fields = list(rows[0].keys()) if rows else []
        with open(path, "rb") as fh:
            self.sha256 = hashlib.sha256(fh.read()).hexdigest()


class Evidence:
    """Resolve {{token}} placeholders against experiment CSV outputs."""

    def __init__(self, round_dir, strict=True):
        self.round_dir = round_dir
        self.exp_root = os.path.join(round_dir, "experiments")
        self.strict = strict
        self._cache = {}
        self.records = []
        self.unresolved = []

    def table(self, relpath, required=()):
        if relpath in self._cache:
            table = self._cache[relpath]
        else:
            path = os.path.join(self.exp_root, relpath.replace("/", os.sep))
            if not os.path.exists(path):
                raise MissingInput("missing experiment output: %s" % relpath)
            with open(path, "r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            if not rows:
                raise MissingInput("empty experiment output: %s" % relpath)
            table = Table(relpath, path, rows)
            self._cache[relpath] = table
        missing = [c for c in required if c not in table.fields]
        if missing:
            raise MissingInput("columns %s missing in %s (has %s)"
                               % (missing, relpath, table.fields))
        return table

    @staticmethod
    def _select(table, where):
        rows = []
        for i, row in enumerate(table.rows):
            if all(str(row.get(k, "")) == str(v) for k, v in where.items()):
                rows.append((i, row))
        return rows

    def value(self, token, spec):
        try:
            table = self.table(spec["file"], spec.get("required", ()))
        except MissingInput as exc:
            self.unresolved.append({"token": token, "reason": str(exc)})
            return None
        where = spec.get("where") or {}
        matches = self._select(table, where)
        if not matches:
            self.unresolved.append({"token": token,
                                    "reason": "no row in %s with %r" % (spec["file"], where)})
            return None
        idx, row = matches[0]
        column = spec.get("column", "value")
        if column not in row:
            self.unresolved.append({"token": token,
                                    "reason": "column %s missing in %s" % (column, spec["file"])})
            return None
        agg = spec.get("agg")
        try:
            if agg == "count":
                number = len(matches)
            elif agg == "nunique":
                number = len({r[column] for _, r in matches})
            elif agg == "sum":
                number = sum(float(r[column]) for _, r in matches)
            elif agg == "mean":
                number = statistics.mean(float(r[column]) for _, r in matches)
            elif agg == "min":
                number = min(float(r[column]) for _, r in matches)
            elif agg == "max":
                number = max(float(r[column]) for _, r in matches)
            else:
                number = float(row[column])
        except (TypeError, ValueError):
            self.unresolved.append({"token": token,
                                    "reason": "non-numeric %s=%r" % (column, row.get(column))})
            return None
        fmt = spec.get("fmt", "{:g}")
        number = float(number) * float(spec.get("scale", 1.0))
        if "d" in fmt:
            number = int(round(number))
        formatted = fmt.format(number)
        self.records.append({
            "token": token,
            "value": number,
            "formatted": formatted,
            "unit": spec.get("unit", ""),
            "source": {"path": table.relpath, "sha256": table.sha256,
                       "row_number_in_file": idx + 2,
                       "column": column, "where": where},
        })
        return formatted

    def resolve_text(self, text, specs):
        def repl(match):
            token = match.group(1)
            spec = specs.get(token)
            if spec is None:
                self.unresolved.append({"token": token,
                                        "reason": "no spec in content module"})
                return "[UNRESOLVED:%s]" % token
            out = self.value(token, spec)
            return out if out is not None else "[UNRESOLVED:%s]" % token
        return TOKEN.sub(repl, text)

    def resolve_cells(self, rows, specs):
        return [[self.resolve_text(str(cell), specs) for cell in row] for row in rows]

    def manifest(self):
        return {"schema": SCHEMA,
                "experiments_root": "research/round8_20261031/experiments",
                "records": self.records,
                "unresolved": self.unresolved}
