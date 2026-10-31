# -*- coding: utf-8 -*-
"""Build Office Math (OMML) for the cost-framework equations of the v2 draft.

The draft used plain-text placeholders such as "c_EV,i = ... (13)".  Word treats
that as body text: it cannot be edited in the equation editor and it reflows like
a sentence.  This module emits real OMML (m:oMath) so that equations 13-15 are
editable equation objects, laid out with a centred tab (formula) and a right tab
(number), which is the layout the rest of the draft uses for numbered equations.

Only the three equations are defined here; equations (1)-(9) come from the frozen
submission and (10)-(12) are still plain text (see the delivery report).
"""
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

NS = nsdecls("m", "w")

DELTA = "\u0394"
MINUS = "\u2212"


def _rpr(italic=False):
    rpr = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:ascii"), "Cambria Math")
    fonts.set(qn("w:hAnsi"), "Cambria Math")
    fonts.set(qn("w:cs"), "Times New Roman")
    rpr.append(fonts)
    if italic:
        rpr.append(OxmlElement("w:i"))
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "000000")
    color.set(qn("w:themeColor"), "text1")
    rpr.append(color)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "24")
    rpr.append(sz)
    szcs = OxmlElement("w:szCs")
    szcs.set(qn("w:val"), "24")
    rpr.append(szcs)
    return rpr


def run(text, italic=False, plain_label=False):
    """One math run. plain_label: upright multi-letter label (EV, ext, ...)."""
    r = OxmlElement("m:r")
    mrpr = OxmlElement("m:rPr")
    sty = OxmlElement("m:sty")
    sty.set(qn("m:val"), "p" if (plain_label or not italic) else "i")
    mrpr.append(sty)
    r.append(mrpr)
    r.append(_rpr(italic and not plain_label))
    t = OxmlElement("m:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    r.append(t)
    return r


def var(text):
    return run(text, italic=True)


def label(text):
    return run(text, plain_label=True)


def textrun(text):
    """Normal text inside math (m:nor): words such as "released in time" stay words.

    Without m:nor, a multi-word string is read as a product of single-letter
    variables by some renderers (LibreOffice turns "in" into the set-membership
    sign), and the words come out letter-spaced and italic.
    """
    r = OxmlElement("m:r")
    mrpr = OxmlElement("m:rPr")
    mrpr.append(OxmlElement("m:nor"))
    r.append(mrpr)
    r.append(_rpr(italic=False))
    t = OxmlElement("m:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    r.append(t)
    return r


def op(text):
    return run(text, plain_label=True)


def sub(base, subscript):
    e = OxmlElement("m:sSub")
    epr = OxmlElement("m:sSubPr")
    ctrl = OxmlElement("m:ctrlPr")
    ctrl.append(_rpr(italic=False))
    epr.append(ctrl)
    e.append(epr)
    e_ = OxmlElement("m:e")
    for child in base:
        e_.append(child)
    e.append(e_)
    s_ = OxmlElement("m:sub")
    for child in subscript:
        s_.append(child)
    e.append(s_)
    return e


def paren(children):
    d = OxmlElement("m:d")
    dpr = OxmlElement("m:dPr")
    ctrl = OxmlElement("m:ctrlPr")
    ctrl.append(_rpr(italic=False))
    dpr.append(ctrl)
    d.append(dpr)
    e = OxmlElement("m:e")
    for child in children:
        e.append(child)
    d.append(e)
    return d


def math(children):
    om = OxmlElement("m:oMath")
    for child in children:
        om.append(child)
    return om


def _eq13():
    return math([
        sub([var("c")], [label("EV"), label(","), var("i")]),
        op("="),
        sub([var("v")], [var("i")]),
        sub([label(DELTA), var("t")], [var("i")]),
        op("+"),
        sub([label(DELTA), var("C")], [label("energy"), label(","), var("i")]),
        op("+"),
        sub([label(DELTA), var("C")], [label("ext"), label(","), var("i")]),
        op("+"),
        sub([var("L")], [label("residual"), label(","), var("i")]),
    ])


def _eq14():
    return math([
        sub([var("c")], [label("ICE"), label(","), var("i")]),
        op("="),
        sub([var("v")], [var("i")]),
        sub([label(DELTA), var("T")], [var("i")]),
        op("+"),
        sub([label(DELTA), var("C")], [label("veh"), label(","), var("i")]),
        op("+"),
        sub([label(DELTA), var("C")], [label("ext"), label(","), var("i")]),
        op("+"),
        sub([var("L")], [label("act"), label(","), var("i")]),
    ])


def _eq15():
    return math([
        sub([label(DELTA), var("C")], [label("occ")]),
        op("="),
        var("C"),
        paren([textrun("occupancy allowed")]),
        op(MINUS),
        var("C"),
        paren([textrun("released in time")]),
    ])


BUILDERS = {"13": _eq13, "14": _eq14, "15": _eq15}


def equation(name):
    """Return the m:oMath element for equation "13"/"14"/"15"."""
    return BUILDERS[name]()
