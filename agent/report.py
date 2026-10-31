"""Render analyst report sections to Markdown and self-contained HTML."""
import html
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Section:
    title: str
    paragraphs: list = field(default_factory=list)
    bullets: list = field(default_factory=list)
    table: pd.DataFrame | None = None
    html_extra: str = ""


def _md_table(df: pd.DataFrame) -> str:
    cols = [df.index.name or ""] + [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for idx, r in df.iterrows():
        lines.append("| " + " | ".join([str(idx)] + [str(v).replace("|", "/") for v in r.values]) + " |")
    return "\n".join(lines)


def to_markdown(title: str, subtitle: str, sections: list) -> str:
    out = [f"# {title}", f"_{subtitle}_", ""]
    for s in sections:
        out.append(f"## {s.title}")
        out += [p + "\n" for p in s.paragraphs]
        out += [f"- {b}" for b in s.bullets]
        if s.bullets:
            out.append("")
        if s.table is not None and not s.table.empty:
            out += [_md_table(s.table), ""]
    return "\n".join(out)


def svg_line_chart(series: pd.Series, width=760, height=220, label="") -> str:
    s = series.dropna()
    if len(s) < 2:
        return ""
    lo, hi = float(s.min()), float(s.max())
    rng = hi - lo or 1.0
    pad = 30
    pts = []
    for i, v in enumerate(s.values):
        x = pad + i * (width - 2 * pad) / (len(s) - 1)
        y = height - pad - (float(v) - lo) / rng * (height - 2 * pad)
        pts.append(f"{x:.1f},{y:.1f}")
    color = "#16a34a" if s.iloc[-1] >= s.iloc[0] else "#dc2626"
    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart">'
        f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(pts)}"/>'
        f'<text x="{pad}" y="16" class="lbl">{html.escape(label)} high {hi:,.0f}</text>'
        f'<text x="{pad}" y="{height - 8}" class="lbl">low {lo:,.0f} | {s.index[0]} → {s.index[-1]}</text>'
        "</svg>"
    )


CSS = """
body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f5f7fb;color:#1f2937}
header{background:#0f172a;color:#fff;padding:22px 36px}header h1{margin:0;font-size:24px}
header p{margin:4px 0 0;color:#cbd5e1}main{padding:20px 36px;max-width:1400px}
section{background:#fff;border-radius:10px;padding:16px 22px;margin-bottom:18px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
h2{font-size:18px;border-bottom:2px solid #e5e7eb;padding-bottom:6px;margin-top:0}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
th{background:#f1f5f9;text-align:left;padding:6px 8px;position:sticky;top:0}
td{padding:5px 8px;border-top:1px solid #eef2f7;vertical-align:top}tr:hover td{background:#fafcff}
.pos{color:#15803d;font-weight:600}.neg{color:#b91c1c;font-weight:600}
.chart{width:100%;max-width:800px;background:#fbfdff;border:1px solid #e5e7eb;border-radius:8px}
.lbl{font-size:11px;fill:#64748b}.disc{font-size:12px;color:#64748b}
"""


def _colorize(cell: str) -> str:
    c = html.escape(str(cell))
    t = str(cell).strip()
    if t.startswith("+") and any(ch.isdigit() for ch in t):
        return f'<span class="pos">{c}</span>'
    if t.startswith("-") and any(ch.isdigit() for ch in t):
        return f'<span class="neg">{c}</span>'
    for word, cls in (("Strong Buy", "pos"), ("Buy", "pos"), ("Accumulate", "pos"), ("Sell", "neg"), ("Reduce", "neg")):
        if t.startswith(word):
            return f'<span class="{cls}">{c}</span>'
    return c


def _html_table(df: pd.DataFrame) -> str:
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in [df.index.name or ""] + list(df.columns))
    body = "".join(
        "<tr>" + f"<td><b>{html.escape(str(i))}</b></td>" + "".join(f"<td>{_colorize(v)}</td>" for v in r.values) + "</tr>"
        for i, r in df.iterrows()
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def to_html(title: str, subtitle: str, sections: list) -> str:
    parts = [f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{CSS}</style></head><body>",
             f"<header><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></header><main>"]
    for s in sections:
        parts.append(f"<section><h2>{html.escape(s.title)}</h2>")
        parts += [f"<p>{html.escape(p)}</p>" for p in s.paragraphs]
        if s.bullets:
            parts.append("<ul>" + "".join(f"<li>{_colorize(b) if b[:1] in '+-' else html.escape(b)}</li>" for b in s.bullets) + "</ul>")
        parts.append(s.html_extra)
        if s.table is not None and not s.table.empty:
            parts.append(_html_table(s.table))
        parts.append("</section>")
    parts.append("</main></body></html>")
    return "".join(parts)
