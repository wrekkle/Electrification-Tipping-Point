#!/usr/bin/env python
"""Public-repository check: links, contract files, path hygiene, syntax.

Scans only files tracked in the public git tree, so the private research workspace present in the
authors' local checkout is neither read nor reported. Exit code 0 means every contract passed.
"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAIL = []
_U = "Us" + "ers"
_PROJ = "Pro" + "jects"
BAD = re.compile(r"C:(?:\\\\|\\|/)" + _U + r"|C:(?:\\\\|\\|/)" + _PROJ + r"|/Users/|research/round8|main_paper/|papers/")


def fail(msg):
    FAIL.append(msg)
    print("FAIL", msg)


def tracked():
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
        return [p for p in out.decode("utf-8", "replace").split("\0") if p]
    except Exception:
        exts = (".py", ".md", ".json", ".yml", ".yaml", ".csv", ".txt")
        out = []
        for d, _, fs in os.walk(ROOT):
            if ".git" in d:
                continue
            for f in fs:
                if f.endswith(exts):
                    out.append(os.path.relpath(os.path.join(d, f), ROOT).replace("\\", "/"))
        return out


def need(rel):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        fail("missing " + rel)
    return p


def check_links():
    text = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    for target in re.findall(r"\]\(([^)#][^)]*)\)", text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if not os.path.exists(os.path.normpath(os.path.join(ROOT, target))):
            fail("README link does not resolve: " + target)


def check_paths(files):
    for rel in files:
        if rel.endswith((".png", ".svg", ".gif", ".jpg")):
            continue
        p = os.path.join(ROOT, rel)
        try:
            text = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for m in BAD.finditer(text):
            fail("private path in %s: %s" % (rel, m.group(0)))


def check_sample():
    p = need("data/sample/parking_events_sample.csv")
    if os.path.exists(p):
        rows = sum(1 for _ in open(p, encoding="utf-8")) - 1
        if rows < 100:
            fail("sample too small: %d rows" % rows)
        else:
            print("PASS sample rows: %d" % rows)


def check_figures():
    fig = need("results/figures")
    if os.path.exists(fig):
        pngs = [f for f in os.listdir(fig) if f.endswith(".png")]
        svgs = [f for f in os.listdir(fig) if f.endswith(".svg")]
        if len(pngs) < 6 or len(svgs) < 6:
            fail("figures incomplete: %d png, %d svg" % (len(pngs), len(svgs)))
        else:
            print("PASS figures: %d png / %d svg" % (len(pngs), len(svgs)))


def check_syntax():
    import compileall
    ok = True
    for d in ("apps", "analysis", "scripts"):
        ok = compileall.compile_dir(os.path.join(ROOT, d), quiet=2) and ok
    if not ok:
        fail("python sources do not compile")
    else:
        print("PASS python sources compile")


def main():
    for rel in ("README.md", "LICENSE.md", "manuscript/README.md", "docs/method.md",
                "docs/data.md", "docs/reproduce.md", "requirements.txt"):
        need(rel)
    files = tracked()
    check_links()
    skip = {"scripts/check_public.py", ".gitignore", "references.bib"}
    check_paths([f for f in files if f not in skip])
    check_sample()
    check_figures()
    check_syntax()
    if FAIL:
        print("\n%d contract(s) failed" % len(FAIL))
        return 1
    print("\nall public contracts passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
