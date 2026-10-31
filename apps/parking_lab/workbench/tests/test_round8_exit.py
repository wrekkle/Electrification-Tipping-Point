# -*- coding: utf-8 -*-
"""Round8 acceptance: the Taipei-specific module really left the execution chain.

Source/DOM-level assertions so a revert or a silent "rename and keep" fails loudly.
Prose mentions are allowed only on lines explicitly marked as historical.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WB = ROOT / "apps" / "parking_lab" / "workbench"
WEB = WB / "web"
EXEC_PATTERNS = ["import datasource", "datasource.", "TaipeiReplay", "DEFAULT_COLLECTION",
                 "data-span", "--collection", "datasource_json", "datasource_available",
                 "taipei_saved_batches"]
HIST_MARKS = ("HISTORICAL", "retired", "not calibrated", "left the execution chain", "historical evidence",
              "不读", "禁止", "不得", "not read")


class TaipeiExitTests(unittest.TestCase):
    def test_datasource_module_is_gone(self):
        self.assertFalse((WB / "datasource.py").exists(), "datasource.py must not exist in the package")
        with self.assertRaises(ModuleNotFoundError):
            __import__("apps.parking_lab.workbench.datasource")

    def test_no_executable_taipei_reference(self):
        hits = []
        for path in WB.rglob("*.py"):
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            hits.extend(f"{path.name}:{p}" for p in EXEC_PATTERNS if p in text)
        self.assertEqual(hits, [], "executable Taipei references: " + "; ".join(hits))

    def test_taipei_prose_is_only_historical(self):
        offenders = []
        for path in WB.rglob("*.py"):
            if "tests" in path.parts:
                continue
            for line in path.read_text(encoding="utf-8").split("\n"):
                if "Taipei" in line or "372" in line:
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    if not any(mark in line for mark in HIST_MARKS):
                        offenders.append(f"{path.name}: {stripped[:80]}")
        self.assertEqual(offenders, [])

    def test_web_ui_has_no_taipei_controls(self):
        for name in ("index.html", "app.js"):
            text = (WEB / name).read_text(encoding="utf-8")
            for token in ("datasource", "replay-taipei", "ds-badge", "ds-refresh"):
                self.assertNotIn(token, text, f"{name} still references {token}")

    def test_server_has_no_datasource_route(self):
        text = (WB / "server.py").read_text(encoding="utf-8")
        for token in ('"/api/datasource"', "datasource_json", "datasource_available"):
            self.assertNotIn(token, text)

    def test_replay_accepts_only_generic_source(self):
        from apps.parking_lab.workbench import continuous
        from apps.parking_lab.workbench.config import Config
        from apps.parking_lab.workbench.simulation import Simulation
        engine = continuous.ContinuousEngine(Simulation(Config()))
        with self.assertRaises(continuous.ContinuousError):
            engine.start_replay("taipei")
        status = engine.start_replay("synthetic")
        self.assertEqual(status["replay"]["source"], "synthetic_ledger")

    def test_audited_modules_have_no_outbound_client(self):
        violations = []
        for path in WB.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    if name.split(".")[0] in {"subprocess", "socket", "requests", "ftplib", "telnetlib"}:
                        violations.append(f"{path.name}: {name}")
                    if name.startswith("urllib.request"):
                        violations.append(f"{path.name}: {name}")
        self.assertEqual(violations, [])

    def test_cli_has_no_collection_argument(self):
        text = (WB / "__main__.py").read_text(encoding="utf-8")
        self.assertNotIn("--collection", text)
        self.assertNotIn("data-span", text)


if __name__ == "__main__":
    unittest.main()
