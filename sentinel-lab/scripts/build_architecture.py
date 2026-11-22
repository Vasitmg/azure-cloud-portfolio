#!/usr/bin/env python3
"""
build_architecture.py - draw docs/architecture.svg with the official service icons.

Usage (from the repo root):
    python3 sentinel-lab/scripts/build_architecture.py

The icons in scripts/icons/ are inlined into the SVG (no external files, no
data: URIs), so the diagram renders on GitHub and works offline.
Sources and terms of the icons: scripts/icons/README.md
"""

import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(HERE, "icons")
LOGO = os.path.join(HERE, "assets", "logo.svg")
OUT = os.path.join(HERE, "..", "docs", "architecture.svg")

W, H = 1160, 800
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'Cascadia Mono', Menlo, Consolas, monospace"

C = {
    "page": "#F6F8FA", "frame": "#D8DEE4", "card": "#FFFFFF", "border": "#D0D7DE",
    "text": "#1F2328", "muted": "#59636E", "faint": "#8C959F", "arrow": "#8C959F",
    "collect": "#0E7C66", "collect_bg": "#E6F4EF", "collect_ink": "#0B4A3D",
    "detect": "#5145B8", "detect_bg": "#EEEDFD", "detect_ink": "#2E2777",
    "deliver": "#57606A", "deliver_bg": "#EEF1F4", "deliver_ink": "#1F2328",
}

_n = 0


def icon(name, x, y, size, fill=None, light_only=False):
    """Inline an SVG file at (x, y), scaled to size; ids and classes get a unique prefix."""
    global _n
    _n += 1
    p = f"i{_n}-"
    path = name if os.path.isabs(name) else os.path.join(ICONS, name)
    with open(path, encoding="utf-8") as f:
        s = f.read()
    s = re.sub(r"<\?xml[^>]*\?>", "", s).strip()
    s = re.sub(r"<title>.*?</title>", "", s, flags=re.S)          # no stray tooltips
    if light_only:                                               # drop dark-mode rules (README images are light)
        s = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^}]*\})*\s*\}", "", s)
    for i in set(re.findall(r'\bid="([^"]+)"', s)):
        s = s.replace(f'id="{i}"', f'id="{p}{i}"').replace(f"#{i})", f"#{p}{i})").replace(f'"#{i}"', f'"#{p}{i}"')
    classes = set()
    for group in re.findall(r'\bclass="([^"]+)"', s):
        classes.update(group.split())
    for cl in sorted(classes, key=len, reverse=True):
        s = re.sub(rf'(?<=[\s"]){re.escape(cl)}(?=[\s"])', p + cl, s)                 # class attributes
        s = re.sub(rf"\.{re.escape(cl)}(?=[\s{{,.:])", "." + p + cl, s)            # <style> selectors
    end = s.index(">")
    root = re.sub(r'\s(width|height|x|y)="[^"]*"', "", s[:end])
    root += f' x="{x}" y="{y}" width="{size}" height="{size}"' + (f' fill="{fill}"' if fill else "")
    return root + s[end:]


# ---------------------------------------------------------------- drawing primitives

def t(x, y, text, size=12, weight=400, fill=None, anchor="start", mono=False, spacing=None):
    fam = f' font-family="{MONO}"' if mono else ""
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill or C["text"]}"'
            f' text-anchor="{anchor}"{fam}{ls}>{html.escape(text)}</text>')


ARROW_KINDS = ("collect", "detect", "deliver")


def arrow(x1, y1, x2, y2, color=None):
    kind = next((k for k in ARROW_KINDS if C[k] == color), "deliver")
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{C[kind]}" stroke-width="1.6"'
            f' marker-end="url(#arr-{kind})"/>')


def markers():
    """One arrowhead per colour (context-stroke is not supported everywhere)."""
    return "".join(
        f'<marker id="arr-{k}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M2 1L8 5L2 9" fill="none" stroke="{C[k]}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></marker>'
        for k in ARROW_KINDS)


def chip_on_line(cx, cy, text, kind, mono=True):
    """Small label sitting on an arrow (e.g. the destination table)."""
    w = 7.0 * len(text) + 16 if mono else 6.2 * len(text) + 18
    return (f'<rect x="{cx - w / 2}" y="{cy - 10}" width="{w}" height="20" rx="10" fill="{C["card"]}"'
            f' stroke="{C[kind]}" stroke-width="1"/>'
            + t(cx, cy + 4, text, 10.5, 600, C[kind], "middle", mono=mono))


def card_bg(x, y, w, h, stroke=None, fill=None, rx=12):
    """Card with a soft two-layer shadow."""
    return (f'<rect x="{x}" y="{y + 3}" width="{w}" height="{h}" rx="{rx}" fill="#1F2328" opacity="0.04"/>'
            f'<rect x="{x}" y="{y + 1}" width="{w}" height="{h}" rx="{rx}" fill="#1F2328" opacity="0.05"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill or C["card"]}"'
            f' stroke="{stroke or C["border"]}" stroke-width="1"/>')


def tile(x, y, kind, ic, size=48, icon_size=30, fill=None):
    off = (size - icon_size) / 2
    return (f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="11" fill="{C[kind + "_bg"]}"/>'
            + icon(ic, x + off, y + off, icon_size, fill=fill))


def step(cx, cy, n, kind):
    """Numbered badge: the order in which an event moves through the lab."""
    return (f'<circle cx="{cx}" cy="{cy}" r="11" fill="{C[kind]}"/>'
            + t(cx, cy + 4, str(n), 11, 700, "#FFFFFF", "middle"))


def card(x, y, w, h, kind, ic, title, sub, n=None, fill=None):
    """Icon tile on the left, title and one detail line, optional step badge."""
    ty = y + (h - 48) / 2
    out = card_bg(x, y, w, h) + tile(x + 16, ty, kind, ic, fill=fill)
    out += t(x + 78, y + h / 2 - 4, title, 14, 650, C[kind + "_ink"])
    out += t(x + 78, y + h / 2 + 15, sub, 12, 400, C["muted"])
    if n:
        out += step(x + w - 22, y + 22, n, kind)
    return out


def centered_card(x, y, w, h, kind, ic, title, lines, n=None, mono_first=False):
    cx = x + w / 2
    out = [card_bg(x, y, w, h), tile(cx - 24, y + 18, kind, ic)]
    out.append(t(cx, y + 92, title, 14.5, 650, C[kind + "_ink"], "middle"))
    for k, line in enumerate(lines):
        out.append(t(cx, y + 113 + 19 * k, line, 12, 400, C["muted"], "middle", mono=mono_first and k == 0))
    if n:
        out.append(step(x + w - 22, y + 22, n, kind))
    return "".join(out)


# ---------------------------------------------------------------- diagram

def build():
    parts = []
    add = parts.append

    add(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="18" fill="{C["page"]}" stroke="{C["frame"]}"/>')

    # ---- header
    if os.path.exists(LOGO):
        add(icon(LOGO, 40, 30, 46, light_only=True))
    add(t(100, 52, "Microsoft Sentinel detection lab", 22, 700))
    add(t(100, 75, "Infrastructure and detections are defined as code in this repository and deployed by GitHub Actions",
          13, 400, C["muted"]))
    x = W - 40
    for label in reversed(["Bicep", "KQL", "Logic Apps", "GitHub Actions"]):
        w = 7.2 * len(label) + 22
        x -= w
        add(f'<rect x="{x}" y="34" width="{w}" height="24" rx="12" fill="{C["card"]}" stroke="{C["border"]}"/>')
        add(t(x + w / 2, 50, label, 11.5, 600, C["muted"], "middle"))
        x -= 8

    # ---- 1 · data sources (centres at x = 205, 580, 955)
    sources = [
        (40, "00007-icon-service-Activity-Log.svg", "Azure Activity Log", "Subscription diagnostic setting", "AzureActivity"),
        (415, "Microsoft-Entra-ID-color-icon.svg", "Microsoft Entra ID audit logs", "Tenant diagnostic setting", "AuditLogs"),
        (790, "10021-icon-service-Virtual-Machine.svg", "Windows Security events", "Test VM (Sweden Central) · AMA + DCR", "SecurityEvent"),
    ]
    for x, ic, title, sub, _ in sources:
        add(card(x, 108, 330, 84, "collect", ic, title, sub, n=1))

    # ---- resource group frame
    add(f'<rect x="40" y="236" width="1080" height="390" rx="18" fill="#FFFFFF" fill-opacity="0.55"'
        f' stroke="{C["faint"]}" stroke-width="1.2" stroke-dasharray="7 6"/>')
    add(icon("10007-icon-service-Resource-Groups.svg", 248, 246, 18))
    add(t(272, 260, "rg-sentinel-lab", 13, 650, "#444C56"))
    add(f'<rect x="384" y="246" width="150" height="20" rx="10" fill="{C["deliver_bg"]}"/>')
    add(t(459, 260, "Germany West Central", 11, 500, C["muted"], "middle"))

    for x, *_rest in sources:
        cx = x + 165
        add(arrow(cx, 192, cx, 282, C["collect"]))
    for x, *_rest, table in sources:
        add(chip_on_line(x + 165, 214, table, "collect"))

    # ---- 2 · workspace
    add(card_bg(64, 284, 1032, 76, stroke=C["collect"]))
    add(tile(80, 298, "collect", "00009-icon-service-Log-Analytics-Workspaces.svg"))
    add(t(142, 318, "Log Analytics workspace · log-sentinel-lab", 15, 650, C["collect_ink"]))
    add(t(142, 338, "90-day retention · 1 GB/day ingestion cap", 12, 400, C["muted"]))
    add(step(1074, 306, 2, "collect"))
    add(arrow(580, 360, 580, 384, C["detect"]))

    # ---- Microsoft Sentinel
    add(f'<rect x="64" y="386" width="1032" height="220" rx="14" fill="{C["detect_bg"]}" stroke="{C["detect"]}" stroke-width="1"/>')
    add(f'<path d="M64 422V400a14 14 0 0 1 14-14h1004a14 14 0 0 1 14 14v22z" fill="{C["detect"]}" opacity="0.08"/>')
    add(icon("10248-icon-service-Azure-Sentinel.svg", 82, 393, 22))
    add(t(112, 409, "Microsoft Sentinel", 14.5, 700, C["detect_ink"]))
    add(t(1078, 409, "SIEM · SOAR", 11, 600, C["detect"], "end", spacing="0.6"))

    # 3 · analytics rules
    add(card_bg(88, 436, 380, 154))
    add(tile(104, 452, "detect", "01085-icon-service-Log-Analytics-Query-Pack.svg", size=40, icon_size=24))
    add(t(156, 477, "Analytics rules (KQL)", 14.5, 650, C["detect_ink"]))
    add(step(446, 458, 3, "detect"))
    rules = [("T1098", "Azure RBAC role assignment"), ("T1098.003", "Entra ID directory role"),
             ("T1562", "Logging / detection tampering"), ("T1110", "Burst of failed logons")]
    for k, (tech, name) in enumerate(rules):
        y = 516 + 21 * k
        add(f'<rect x="104" y="{y - 13}" width="82" height="18" rx="9" fill="{C["detect_bg"]}"/>')
        add(t(145, y, tech, 10.5, 650, C["detect"], "middle", mono=True))
        add(t(198, y, name, 12.5, 400, C["text"]))

    # 4 · incidents, 5 · playbook
    add(centered_card(516, 436, 228, 154, "detect", "00002-icon-service-Alerts.svg", "Incidents",
                      ["Alerts grouped into cases", "Account, IP, host entities"], n=4))
    add(centered_card(792, 436, 280, 154, "detect", "02631-icon-service-Logic-Apps.svg", "Playbook (Logic App)",
                      ["pb-incident-email", "Automation rule: on incident created"], n=5, mono_first=True))
    add(arrow(468, 513, 514, 513, C["detect"]))
    add(arrow(744, 513, 790, 513, C["detect"]))

    # ---- 6 · email
    add(arrow(932, 590, 932, 678, C["deliver"]))
    add(chip_on_line(932, 646, "Outlook connector", "deliver", mono=False))
    add(card(812, 680, 260, 76, "deliver", "octicons/mail-24.svg", "Email to analyst",
             "Severity, title, incident link", n=6, fill=C["deliver_ink"]))

    # ---- delivery pipeline
    add(t(40, 668, "CONTINUOUS DEPLOYMENT", 10.5, 700, C["faint"], spacing="1"))
    add(card(40, 680, 290, 76, "deliver", "octicons/mark-github-16.svg", "GitHub repository",
             "Bicep · KQL · scripts", fill=C["deliver_ink"]))
    add(arrow(330, 718, 374, 718, C["deliver"]))
    add(card(376, 680, 350, 76, "deliver", "octicons/workflow-24.svg", "GitHub Actions",
             "OIDC, no secrets · lint → what-if → deploy", fill=C["deliver_ink"]))
    add(arrow(551, 680, 551, 628, C["deliver"]))
    add(chip_on_line(551, 652, "deploys", "deliver", mono=False))

    # ---- legend
    y = 780
    x = 40
    for kind, label in [("collect", "Data collection"), ("detect", "Detection and response"),
                        ("deliver", "Delivery and notification")]:
        add(f'<rect x="{x}" y="{y - 11}" width="14" height="14" rx="4" fill="{C[kind + "_bg"]}" stroke="{C[kind]}"/>')
        add(t(x + 22, y, label, 12, 400, C["muted"]))
        x += 22 + 6.8 * len(label) + 28
    add(step(x + 11, y - 4, 1, "deliver"))
    add(t(x + 28, y, "Order of events", 12, 400, C["muted"]))
    add(t(W - 40, y, "Icons: Microsoft Azure, Microsoft Entra, GitHub Octicons", 11, 400, C["faint"], "end"))

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}" role="img" aria-labelledby="t d">
  <title id="t">Microsoft Sentinel detection lab – architecture</title>
  <desc id="d">Three data sources feed a Log Analytics workspace with Microsoft Sentinel. Four KQL analytics rules create incidents, and a Logic App playbook emails the analyst. Everything is deployed from GitHub with GitHub Actions using OIDC.</desc>
  <defs>{markers()}</defs>
  {"".join(parts)}
</svg>
"""


if __name__ == "__main__":
    svg = build()
    out = os.path.abspath(OUT)
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Wrote {out} ({len(svg) // 1024} KB)")
