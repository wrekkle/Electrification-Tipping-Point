# -*- coding: utf-8 -*-
"""Minimal YAML-subset reader and configuration contract for the PREI package.

The bundled Python has no PyYAML, so this module implements the small subset
used by configs/: nested mappings by indentation, block lists of scalars or
inline flow maps/lists, comments, quoted strings, ints, floats, booleans.

Every *model parameter* is written as {value: ..., source: ...} where
source is one of manuscript / assumption / sensitivity.  Structural settings
(meta, scenario lists) may be plain values.  Config.params collects all
parameter leaves; Config.resolved() returns a plain nested dict of values.
"""
from __future__ import annotations

import hashlib
import os
import re

SOURCE_KINDS = ("manuscript", "assumption", "sensitivity")


class ConfigError(ValueError):
    pass


# --------------------------------------------------------------------------
# YAML subset parser
# --------------------------------------------------------------------------
def _strip_comment(line):
    out, quote, depth = [], None, 0
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch in "[{":
            depth += 1
            out.append(ch)
        elif ch in "]}":
            depth -= 1
            out.append(ch)
        elif ch == "#" and depth == 0:
            break
        else:
            out.append(ch)
    return "".join(out)


class _FlowParser:
    def __init__(self, text):
        self.s = text
        self.i = 0

    def skip(self):
        while self.i < len(self.s) and self.s[self.i] in " \t":
            self.i += 1

    def parse(self):
        self.skip()
        ch = self.s[self.i]
        if ch == "[":
            return self.parse_list()
        if ch == "{":
            return self.parse_map()
        return self.parse_atom()

    def parse_atom(self):
        self.skip()
        start = self.i
        quote = None
        while self.i < len(self.s):
            ch = self.s[self.i]
            if quote:
                if ch == quote:
                    quote = None
                self.i += 1
            elif ch in "\"'":
                quote = ch
                self.i += 1
            elif ch in ",]}":
                break
            else:
                self.i += 1
        return _scalar(self.s[start:self.i].strip())

    def parse_list(self):
        self.i += 1
        out = []
        while True:
            self.skip()
            if self.i >= len(self.s):
                raise ConfigError("unterminated flow list")
            if self.s[self.i] == "]":
                self.i += 1
                return out
            out.append(self.parse())
            self.skip()
            if self.i < len(self.s) and self.s[self.i] == ",":
                self.i += 1

    def parse_map(self):
        self.i += 1
        out = {}
        while True:
            self.skip()
            if self.i >= len(self.s):
                raise ConfigError("unterminated flow map")
            if self.s[self.i] == "}":
                self.i += 1
                return out
            key_start = self.i
            while self.i < len(self.s) and self.s[self.i] not in ":}":
                self.i += 1
            key = self.s[key_start:self.i].strip().strip("\"'")
            if self.i >= len(self.s) or self.s[self.i] != ":":
                raise ConfigError("expected ':' in flow map near %r" % self.s[key_start:])
            self.i += 1
            out[key] = self.parse()
            self.skip()
            if self.i < len(self.s) and self.s[self.i] == ",":
                self.i += 1


def _scalar(text):
    text = text.strip()
    if text == "":
        return None
    if text[0] in "[{":
        return _FlowParser(text).parse()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~", "none"):
        return None
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    try:
        return float(text)
    except ValueError:
        return text


def _tokenize(text):
    rows = []
    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        rows.append((indent, line.strip()))
    return rows


def _parse_block(rows, i, indent):
    if i < len(rows) and rows[i][1].startswith("- "):
        out = []
        while i < len(rows) and rows[i][0] == indent and rows[i][1].startswith("- "):
            item = rows[i][1][2:].strip()
            i += 1
            if item == "":
                if i < len(rows) and rows[i][0] > indent:
                    val, i = _parse_block(rows, i, rows[i][0])
                else:
                    val = None
                out.append(val)
            else:
                out.append(_scalar(item))
        return out, i
    out = {}
    while i < len(rows) and rows[i][0] == indent:
        content = rows[i][1]
        if content.startswith("- "):
            raise ConfigError("unexpected list item in mapping: %r" % content)
        if ":" not in content:
            raise ConfigError("expected 'key: value', got %r" % content)
        key, _, rest = content.partition(":")
        key, rest = key.strip(), rest.strip()
        i += 1
        if rest != "":
            out[key] = _scalar(rest)
        elif i < len(rows) and rows[i][0] > indent:
            out[key], i = _parse_block(rows, i, rows[i][0])
        else:
            out[key] = None
    return out, i


def parse_yaml_text(text):
    rows = _tokenize(text)
    if not rows:
        return {}
    tree, i = _parse_block(rows, 0, rows[0][0])
    if i != len(rows):
        raise ConfigError("trailing content at line %r" % (rows[i],))
    return tree


# --------------------------------------------------------------------------
# Parameter contract
# --------------------------------------------------------------------------
def _is_param(node):
    return isinstance(node, dict) and "value" in node and "source" in node


class Config:
    def __init__(self, tree, path="<memory>"):
        self.path = path
        self.tree = tree
        self.params = {}
        self._walk(tree, "")

    def _walk(self, node, prefix):
        if isinstance(node, dict):
            if _is_param(node):
                self.params[prefix] = node
                return
            for key, val in node.items():
                self._walk(val, (prefix + "." + key) if prefix else key)
        elif isinstance(node, list):
            for idx, val in enumerate(node):
                self._walk(val, "%s[%d]" % (prefix, idx))

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        return cls(parse_yaml_text(text), path)

    def value(self, path):
        if path not in self.params:
            raise ConfigError("unknown parameter %r in %s" % (path, self.path))
        return self.params[path]["value"]

    def source(self, path):
        return self.params[path]["source"]

    def has(self, path):
        return path in self.params

    def resolved(self):
        def build(node):
            if isinstance(node, dict):
                if _is_param(node):
                    return node["value"]
                return {k: build(v) for k, v in node.items()}
            if isinstance(node, list):
                return [build(v) for v in node]
            return node
        return build(self.tree)

    def source_map(self):
        return {k: v["source"] for k, v in self.params.items()}

    def validate(self, required=(), choices=None, source_check=True):
        choices = choices or {}
        missing = [p for p in required if p not in self.params]
        if missing:
            raise ConfigError("missing required parameters: %s" % ", ".join(missing))
        if source_check:
            for path, node in self.params.items():
                if node.get("source") not in SOURCE_KINDS:
                    raise ConfigError(
                        "parameter %r has invalid source %r (allowed: %s)"
                        % (path, node.get("source"), ", ".join(SOURCE_KINDS)))
        for path, allowed in choices.items():
            val = self.value(path)
            if val not in allowed:
                raise ConfigError("parameter %r = %r not in %r" % (path, val, allowed))
        return self

    def apply_overrides(self, overrides):
        values = self.resolved()
        for path, raw in overrides.items():
            parts = path.split(".")
            node = values
            for part in parts[:-1]:
                node = node[part]
            node[parts[-1]] = raw
        merged = Config(values, self.path + "::override")
        for path, node in merged.params.items():
            if path in self.params:
                node["source"] = self.params[path]["source"]
            else:
                node["source"] = "sensitivity"
        return merged


def load_config(path):
    if not os.path.exists(path):
        raise ConfigError("config not found: %s" % path)
    return Config.load(path)


def derive_seed(seed, *labels):
    """Stable seed derivation (does not depend on Python's salted hash)."""
    text = "|".join([str(seed)] + [str(x) for x in labels]).encode("utf-8")
    digest = hashlib.sha256(text).hexdigest()
    return int(digest[:8], 16)
