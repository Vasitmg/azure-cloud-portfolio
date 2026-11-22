#!/usr/bin/env python3
"""
rg_report.py - build an HTML overview of the Sentinel lab resource group.

Uses the Azure CLI session you already have (az login), calls Azure
Resource Manager GET APIs and writes one self-contained HTML file.
No tokens or secrets are written to the file.

Usage (from the repo root):
    python3 sentinel-lab/scripts/rg_report.py
    python3 sentinel-lab/scripts/rg_report.py --resource-group rg-sentinel-lab --workspace log-sentinel-lab
    open sentinel-lab/reports/rg-report.html

The report can contain user names and IDs from your tenant, so the
reports/ folder is git-ignored. Do not commit it to a public repo.

Icons: official Microsoft Azure Architecture Icons (V25), stored unmodified
in scripts/icons/ and embedded into the report. Source and terms:
https://learn.microsoft.com/azure/architecture/icons/

World map: Natural Earth 1:110m land (public domain), via the world-atlas
package (ISC), stored in scripts/assets/land-110m.json. Region coordinates
come from 'az account list-locations'.
"""

import argparse
import base64
import datetime as dt
import html
import json
import math
import os
import re
import subprocess
import sys

ARM = "https://management.azure.com"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(SCRIPT_DIR, "icons")
LAND_FILE = os.path.join(SCRIPT_DIR, "assets", "land-110m.json")
LOGO_FILE = os.path.join(SCRIPT_DIR, "assets", "logo.svg")        # Sentinel Lab logo (header)
FAVICON_FILE = os.path.join(SCRIPT_DIR, "assets", "favicon.svg")  # heavier cut for 16-32 px tabs

# Official Azure Architecture Icons (file names as shipped by Microsoft)
ICON_FILES = {
    "rg": "10007-icon-service-Resource-Groups.svg",
    "law": "00009-icon-service-Log-Analytics-Workspaces.svg",
    "sentinel": "10248-icon-service-Azure-Sentinel.svg",
    "logic": "02631-icon-service-Logic-Apps.svg",
    "apiconn": "10048-icon-service-API-Connections.svg",
    "solution": "00021-icon-service-Solutions.svg",
    "activity": "00007-icon-service-Activity-Log.svg",
    "diag": "00008-icon-service-Diagnostics-Settings.svg",
    "tenant": "02679-icon-service-Tenant-Properties.svg",
    "alerts": "00002-icon-service-Alerts.svg",
    "sub": "10002-icon-service-Subscriptions.svg",
}

# resource type -> (friendly name, icon key)
TYPE_INFO = {
    "microsoft.logic/workflows": ("Logic App", "logic"),
    "microsoft.operationalinsights/workspaces": ("Log Analytics workspace", "law"),
    "microsoft.operationsmanagement/solutions": ("Solution", "solution"),
    "microsoft.web/connections": ("API connection", "apiconn"),
}


# ---------------------------------------------------------------- Azure calls

def az(*args):
    """Run an az command and return parsed JSON (or None on error)."""
    cmd = ["az", *args, "-o", "json"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(out.stdout) if out.stdout.strip() else None
    except FileNotFoundError:
        sys.exit("Azure CLI (az) not found. Install it and run 'az login' first.")
    except subprocess.CalledProcessError as e:
        print(f"  ! {' '.join(args[:3])} failed: {e.stderr.strip().splitlines()[-1] if e.stderr else e}")
        return None


def az_get(url):
    """GET an ARM REST URL with az rest. Returns the 'value' list or the object."""
    data = az("rest", "--method", "get", "--url", url)
    if isinstance(data, dict) and "value" in data:
        return data["value"]
    return data


# ---------------------------------------------------------------- HTML helpers

_icon_cache = {}


def icon_uri(key):
    """Official icon as a data URI ('' if unknown or missing)."""
    if key not in _icon_cache:
        path = os.path.join(ICON_DIR, ICON_FILES.get(key, ""))
        try:
            with open(path, "rb") as f:
                _icon_cache[key] = "data:image/svg+xml;base64," + base64.b64encode(f.read()).decode()
        except OSError:
            _icon_cache[key] = ""
    return _icon_cache[key]


def file_uri(path):
    """Any local SVG as a data URI ('' if missing)."""
    try:
        with open(path, "rb") as f:
            return "data:image/svg+xml;base64," + base64.b64encode(f.read()).decode()
    except OSError:
        return ""


def resource_kind(r):
    """(friendly type name, icon key or None) for an ARM resource."""
    rtype = r.get("type", "")
    if rtype.lower() == "microsoft.operationsmanagement/solutions" and r.get("name", "").startswith("SecurityInsights"):
        return "Microsoft Sentinel", "sentinel"
    return TYPE_INFO.get(rtype.lower(), (rtype.split("/", 1)[-1], None))


def icon(key, size=20, cls="ic"):
    """Return an <img> with the official icon embedded as a data URI."""
    src = icon_uri(key) if key else ""
    if not src:
        return f'<span class="{cls} ic-missing" style="width:{size}px;height:{size}px"></span>'
    return f'<img class="{cls}" src="{src}" width="{size}" height="{size}" alt="">'


def esc(v):
    return html.escape("" if v is None else str(v))


def table(headers, rows, empty="Nothing found.", cls=""):
    if not rows:
        return f'<div class="empty">{esc(empty)}</div>'
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


SEV_KIND = {"High": "high", "Medium": "med", "Low": "low", "Informational": "info"}
STATUS_KIND = {"New": "new", "Active": "active", "Closed": "closed"}


def sev(s):
    return f'<span class="sev {SEV_KIND.get(s, "info")}"><i></i>{esc(s or "–")}</span>'


def pill(text, kind=""):
    return f'<span class="pill {kind}">{esc(text)}</span>'


def chips(items, kind=""):
    return '<span class="chips">' + "".join(f'<span class="chip {kind}">{esc(i)}</span>' for i in items) + "</span>"


def split_camel(s):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s or "")


def iso_duration(s):
    """PT1H -> '1 h', PT5M -> '5 min', P1D -> '1 day'."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", s or "")
    if not m or not any(m.groups()):
        return s or ""
    d, h, mi = m.groups()
    parts = []
    if d:
        parts.append(f"{d} day" + ("s" if d != "1" else ""))
    if h:
        parts.append(f"{h} h")
    if mi:
        parts.append(f"{mi} min")
    return " ".join(parts)


def technique_links(techniques):
    out = []
    for t in techniques or []:
        url = "https://attack.mitre.org/techniques/" + t.replace(".", "/") + "/"
        out.append(f'<a class="chip mitre" href="{esc(url)}" target="_blank" rel="noopener">{esc(t)}</a>')
    return '<span class="chips">' + "".join(out) + "</span>" if out else '<span class="muted">–</span>'


def land_dots(step=1.3):
    """Turn the Natural Earth land outline into a dot grid: flat list of lat*10, lon*10."""
    try:
        with open(LAND_FILE, encoding="utf-8") as f:
            topo = json.load(f)
    except (OSError, ValueError):
        return []
    (sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:  # TopoJSON arcs are delta-encoded and quantized
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(idx):
        out = []
        for i in idx:
            pts = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(pts if not out else pts[1:])
        return out

    obj = topo["objects"]["land"]
    polys = []
    for geom in obj.get("geometries", [obj]):
        parts = geom["arcs"] if geom["type"] == "MultiPolygon" else [geom["arcs"]] if geom["type"] == "Polygon" else []
        for poly in parts:
            rings = [ring(r) for r in poly]
            xs = [p[0] for p in rings[0]]
            ys = [p[1] for p in rings[0]]
            polys.append((min(xs), max(xs), min(ys), max(ys), rings))

    def inside(px, py, pts):
        hit, j = False, len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
                hit = not hit
            j = i
        return hit

    dots = []
    lat = -90 + step / 2
    while lat < 90:
        lon_step = step / max(math.cos(math.radians(lat)), 0.15)  # equal spacing on the sphere
        lon = -180 + lon_step / 2
        while lon < 180:
            for x0, x1, y0, y1, rings in polys:
                if x0 <= lon <= x1 and y0 <= lat <= y1 and inside(lon, lat, rings[0]) \
                        and not any(inside(lon, lat, h) for h in rings[1:]):
                    dots += [round(lat * 10), round(lon * 10)]
                    break
            lon += lon_step
        lat += step
    return dots


def world_data(groups, all_resources, locations, current_rg):
    """Data for the globe: every resource group with its region coordinates and resources."""
    locs = {}
    for loc in locations or []:
        m = loc.get("metadata") or {}
        try:
            locs[loc["name"]] = (loc.get("displayName") or loc["name"], float(m["latitude"]), float(m["longitude"]))
        except (KeyError, TypeError, ValueError):
            pass

    by_rg = {}
    for r in all_resources:
        by_rg.setdefault((r.get("resourceGroup") or "").lower(), []).append(r)

    used, out = {"rg"}, []
    for g in sorted(groups, key=lambda g: g.get("name", "").lower()):
        name, loc = g.get("name", ""), g.get("location", "")
        region, lat, lon = locs.get(loc, (loc, None, None))
        res = []
        for r in sorted(by_rg.get(name.lower(), []), key=lambda r: (r.get("type", "").lower(), r.get("name", ""))):
            friendly, key = resource_kind(r)
            if key:
                used.add(key)
            res.append({"id": r.get("id"), "name": r.get("name"), "type": r.get("type"), "friendly": friendly,
                        "location": locs.get(r.get("location"), (r.get("location"),))[0], "icon": key})
        out.append({"name": name, "location": loc, "region": region, "lat": lat, "lon": lon,
                    "tags": [f"{k}={v}" for k, v in (g.get("tags") or {}).items()],
                    "current": name.lower() == current_rg.lower(), "resources": res})
    return {"groups": out, "icons": {k: icon_uri(k) for k in sorted(used) if icon_uri(k)}, "dots": land_dots()}


def name_cell(icon_key, name, sub=""):
    sub_html = f'<span class="sub">{esc(sub)}</span>' if sub else ""
    return f'<span class="nm">{icon(icon_key)}<span><b>{esc(name)}</b>{sub_html}</span></span>'


# ---------------------------------------------------------------- page

CSS = """
:root {
  /* Layout: one 1120px column; header band, stat row, then sections with anchors */
  --bg:#f5f7fa; --surface:#ffffff; --surface-2:#eef2f6; --text:#18202a; --muted:#5b6876; --line:#dde3ea;
  --accent:#0f6cbd; --accent-soft:#e3effa;
  --high:#b42318; --high-bg:#fdecea; --med:#a15c07; --med-bg:#fdf3e1; --low:#1f6f43; --low-bg:#e6f4ec;
  --info:#5b6876; --info-bg:#eef2f6; --new:#0f6cbd; --new-bg:#e3effa;
  --globe-ocean:#d6e4f2; --globe-ocean-2:#f1f7fd; --globe-land:#4d6f93; --globe-rim:#b9cce0;
  --font: "Segoe UI Variable Text", "Segoe UI", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  --mono: ui-monospace, "Cascadia Mono", SFMono-Regular, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root {
  --bg:#11161c; --surface:#181f27; --surface-2:#202a35; --text:#e6ebf0; --muted:#98a5b3; --line:#2b3642;
  --accent:#5caeff; --accent-soft:#16304a;
  --high:#ff9b8f; --high-bg:#3d1714; --med:#f5c06a; --med-bg:#3a2908; --low:#8fd6a9; --low-bg:#123222;
  --info:#a9b5c2; --info-bg:#24303c; --new:#7cc0ff; --new-bg:#16304a; color-scheme:dark;
  --globe-ocean:#0d1d2c; --globe-ocean-2:#1a3550; --globe-land:#7fb6e6; --globe-rim:#2c4a66;
} }
* { box-sizing:border-box; }
body { margin:0; font:14px/1.55 var(--font); background:var(--bg); color:var(--text); -webkit-font-smoothing:antialiased; }
a { color:var(--accent); }
.muted { color:var(--muted); }
header.top { background:var(--surface); border-bottom:1px solid var(--line); }
.wrap { max-width:1120px; margin:0 auto; padding-inline:max(20px, env(safe-area-inset-left, 0px)); }
.hero { display:flex; gap:16px; align-items:center; padding-block:28px 20px; }
.hero .ic-lg { flex:none; width:44px; height:44px; padding:8px; border-radius:10px; background:var(--accent-soft); }
.hero .brand { flex:none; width:48px; height:48px; }
.eyebrow { font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }
h1 { font-size:26px; line-height:1.2; font-weight:600; margin:2px 0 0; }
.meta { display:flex; flex-wrap:wrap; gap:8px; padding-bottom:18px; }
.meta span { display:inline-flex; align-items:center; gap:6px; font-size:12.5px; color:var(--muted);
  background:var(--surface-2); border-radius:6px; padding:4px 10px; }
.meta b { color:var(--text); font-weight:600; }
nav.toc { display:flex; gap:4px; overflow-x:auto; border-top:1px solid var(--line); }
nav.toc a { color:var(--muted); text-decoration:none; font-size:13px; padding:10px 12px; border-bottom:2px solid transparent; white-space:nowrap; }
nav.toc a:hover, nav.toc a:focus-visible { color:var(--text); border-bottom-color:var(--accent); outline:none; }
main { display:flex; flex-direction:column; gap:36px; padding-block:28px 48px; }
.stats { display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:12px; }
.stat { display:flex; gap:14px; align-items:flex-start; background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:16px; }
.stat img { flex:none; margin-top:2px; }
.stat .n { font-size:28px; line-height:1; font-weight:600; font-variant-numeric:tabular-nums; }
.stat .l { font-size:13px; color:var(--text); margin-top:6px; }
.stat .s { font-size:12px; color:var(--muted); margin-top:2px; }
.stat.alert { border-color:var(--high); box-shadow:inset 3px 0 0 var(--high); }
section { display:flex; flex-direction:column; gap:12px; scroll-margin-top:16px; }
.sh { display:flex; align-items:center; gap:10px; }
.sh h2 { font-size:17px; font-weight:600; margin:0; }
.sh .count { font-size:12px; color:var(--muted); background:var(--surface-2); border-radius:999px; padding:1px 9px; font-variant-numeric:tabular-nums; }
.sh .hint { margin-left:auto; font-size:12px; color:var(--muted); }
.tw { background:var(--surface); border:1px solid var(--line); border-radius:10px; overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:13.5px; }
th { text-align:left; font-weight:600; color:var(--muted); font-size:11.5px; letter-spacing:.04em; text-transform:uppercase;
  padding:10px 14px; border-bottom:1px solid var(--line); background:var(--surface-2); white-space:nowrap; }
td { padding:11px 14px; border-bottom:1px solid var(--line); vertical-align:middle; }
tr:last-child td { border-bottom:none; }
tbody tr:hover td { background:color-mix(in srgb, var(--surface-2) 55%, transparent); }
.nm { display:flex; align-items:center; gap:10px; min-width:200px; }
.nm > span { display:flex; flex-direction:column; }
.nm b { font-weight:600; }
.sub { font-family:var(--mono); font-size:11.5px; color:var(--muted); }
.ic { flex:none; }
.ic-missing { display:inline-block; border-radius:4px; background:var(--line); }
.chips { display:flex; flex-wrap:wrap; gap:4px; }
.chip { font-size:12px; border:1px solid var(--line); border-radius:5px; padding:1px 7px; background:var(--surface); white-space:nowrap; }
.chip.tag { font-family:var(--mono); font-size:11.5px; background:var(--surface-2); border-color:transparent; }
.chip.mitre { font-family:var(--mono); font-size:11.5px; text-decoration:none; color:var(--accent); border-color:color-mix(in srgb, var(--accent) 40%, transparent); }
.chip.mitre:hover { background:var(--accent-soft); }
.sev { display:inline-flex; align-items:center; gap:6px; font-size:12.5px; font-weight:600; padding:2px 9px 2px 7px; border-radius:999px; white-space:nowrap; }
.sev i { width:7px; height:7px; border-radius:50%; background:currentColor; }
.sev.high { color:var(--high); background:var(--high-bg); }
.sev.med { color:var(--med); background:var(--med-bg); }
.sev.low { color:var(--low); background:var(--low-bg); }
.sev.info { color:var(--info); background:var(--info-bg); }
.pill { display:inline-block; font-size:12px; padding:1px 9px; border-radius:5px; background:var(--info-bg); color:var(--info); white-space:nowrap; }
.pill.ok { background:var(--low-bg); color:var(--low); }
.pill.off { background:var(--info-bg); color:var(--muted); }
.pill.new { background:var(--new-bg); color:var(--new); }
.pill.active { background:var(--med-bg); color:var(--med); }
.pill.closed { background:var(--info-bg); color:var(--muted); }
.num { font-family:var(--mono); font-variant-numeric:tabular-nums; color:var(--muted); }
.when { font-variant-numeric:tabular-nums; white-space:nowrap; color:var(--muted); }
.flows { display:grid; gap:10px; }
.flow { display:grid; grid-template-columns:minmax(220px, 1.2fr) auto minmax(160px, .8fr) 2fr; gap:16px; align-items:center;
  background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }
.flow .arrow { color:var(--muted); font-size:18px; }
.flow .lbl { font-size:11px; letter-spacing:.05em; text-transform:uppercase; color:var(--muted); margin-bottom:4px; }
@media (max-width:760px) { .flow { grid-template-columns:1fr; gap:8px; } .flow .arrow { display:none; } }
.empty { background:var(--surface); border:1px dashed var(--line); border-radius:10px; padding:18px; color:var(--muted); text-align:center; }
.world { display:grid; grid-template-columns:minmax(0, 1.4fr) minmax(260px, 1fr); gap:16px; align-items:stretch; }
@media (max-width:860px) { .world { grid-template-columns:1fr; } }
.globe-wrap { position:relative; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px;
  background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:16px; min-width:0; }
#globe { display:block; touch-action:none; cursor:grab; max-width:100%; border-radius:50%; }
#globe:active { cursor:grabbing; }
#globe:focus-visible { outline:2px solid var(--accent); outline-offset:6px; }
.globe-tip { position:absolute; pointer-events:none; background:var(--text); color:var(--bg); font-size:12px; line-height:1.4;
  padding:5px 9px; border-radius:6px; white-space:nowrap; z-index:2; }
.globe-tip span { opacity:.75; }
.globe-hint { font-size:12px; color:var(--muted); text-align:center; }
.rg-panel { display:flex; flex-direction:column; gap:10px; background:var(--surface); border:1px solid var(--line);
  border-radius:10px; padding:12px; min-width:0; max-height:600px; }
.rg-panel input { font:inherit; font-size:13.5px; padding:8px 10px; border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--text); }
.rg-panel input:focus-visible { outline:2px solid var(--accent); outline-offset:1px; }
.rg-list { display:flex; flex-direction:column; gap:4px; overflow-y:auto; min-height:0; }
.rg-group { border:1px solid transparent; border-radius:8px; }
.rg-group.on { background:var(--accent-soft); border-color:color-mix(in srgb, var(--accent) 45%, transparent); }
.rg-item { display:flex; align-items:center; gap:10px; width:100%; text-align:left; font:inherit; color:inherit; background:transparent;
  border:0; border-radius:8px; padding:8px 10px 8px 6px; cursor:pointer; }
.rg-group:not(.on) .rg-item:hover { background:var(--surface-2); }
.rg-item:focus-visible { outline:2px solid var(--accent); outline-offset:1px; }
.chev { flex:none; width:14px; text-align:center; color:var(--muted); font-size:16px; line-height:1; transition:transform .15s; }
.rg-group.open .chev { transform:rotate(90deg); color:var(--accent); }
@media (prefers-reduced-motion: reduce) { .chev { transition:none; } }
.rg-res { padding:0 10px 10px 30px; display:flex; flex-direction:column; gap:8px; }
.rg-res ul { list-style:none; margin:0; padding:0 0 0 12px; border-left:1px solid color-mix(in srgb, var(--accent) 35%, transparent);
  display:flex; flex-direction:column; gap:2px; }
.rg-res li { display:flex; align-items:center; gap:9px; padding:6px 8px; border-radius:6px; background:var(--surface); }
.rg-res .rg-txt b { font-weight:500; font-size:13px; }
.rg-tags { padding-left:12px; }
.rg-none { font-size:12.5px; color:var(--muted); padding-left:12px; }
.rg-open { flex:none; text-decoration:none; font-size:14px; line-height:1; padding:4px 6px; border-radius:5px; color:var(--muted); }
.rg-open:hover, .rg-open:focus-visible { color:var(--accent); background:var(--accent-soft); outline:none; }
.rg-txt { display:flex; flex-direction:column; min-width:0; flex:1; }
.rg-txt b { font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.rg-txt span { font-size:12px; color:var(--muted); }
.rg-txt .rg-cur { color:var(--accent); }
.rg-n { flex:none; font-size:12px; font-variant-numeric:tabular-nums; color:var(--muted); background:var(--surface-2); border-radius:999px; padding:1px 8px; }
footer { border-top:1px solid var(--line); padding-block:18px 32px; font-size:12px; color:var(--muted); display:flex; flex-wrap:wrap; gap:6px 18px; justify-content:space-between; }
"""

# Interactive globe: orthographic projection drawn on a canvas, no libraries.
WORLD_JS = r"""
(function () {
  const dataEl = document.getElementById("world-data");
  if (!dataEl) return;
  const data = JSON.parse(dataEl.textContent);
  const groups = data.groups || [], icons = data.icons || {};
  const canvas = document.getElementById("globe"), ctx = canvas.getContext("2d");
  const wrap = canvas.parentElement, tip = document.getElementById("globe-tip");
  const listEl = document.getElementById("rg-list");
  const filterEl = document.getElementById("rg-filter");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const RAD = Math.PI / 180;

  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, ch =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch]));
  const iconHtml = (k, px) => icons[k]
    ? `<img class="ic" src="${icons[k]}" width="${px}" height="${px}" alt="">`
    : `<span class="ic ic-missing" style="width:${px}px;height:${px}px"></span>`;
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  const transparent = col => {   // same hue at alpha 0, so gradients do not fade through grey
    const m = /^#([0-9a-f]{6})$/i.exec(col);
    if (!m) return "rgba(0,0,0,0)";
    const v = parseInt(m[1], 16);
    return `rgba(${v >> 16},${(v >> 8) & 255},${v & 255},0)`;
  };

  // Land dots: precompute sin/cos of latitude once
  const raw = data.dots || [], n = raw.length >> 1;
  const dSin = new Float32Array(n), dCos = new Float32Array(n), dLon = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const la = raw[2 * i] / 10 * RAD;
    dSin[i] = Math.sin(la); dCos[i] = Math.cos(la); dLon[i] = raw[2 * i + 1] / 10 * RAD;
  }

  // One pin per Azure region, holding every resource group in it
  const regions = [], byLoc = {};
  groups.forEach((g, i) => {
    if (g.lat == null || g.lon == null) return;
    let r = byLoc[g.location];
    if (!r) { r = byLoc[g.location] = {name: g.region, lat: g.lat, lon: g.lon, groups: []}; regions.push(r); }
    r.groups.push(i);
  });

  const clampLat = v => Math.max(-70, Math.min(70, v));
  let selected = -1, open = false, pins = [], colors = {};
  let first = groups.findIndex(g => g.current);
  if (first < 0 && groups.length) first = 0;
  const home = first >= 0 && groups[first].lat != null ? groups[first] : null;
  const view = {lon: home ? home.lon : 10, lat: home ? clampLat(home.lat * 0.6) : 20};
  let size = 0, R = 0, c = 0, dpr = 1, needsDraw = true;
  let spinning = !reduceMotion, anim = null, dragging = false, moved = false, start = null;

  function readColors() {
    const cs = getComputedStyle(document.documentElement), v = k => cs.getPropertyValue(k).trim();
    colors = {ocean: v("--globe-ocean"), ocean2: v("--globe-ocean-2"), land: v("--globe-land"), rim: v("--globe-rim"),
              accent: v("--accent"), glow: v("--accent-soft"), surface: v("--surface"), text: v("--text")};
    needsDraw = true;
  }

  function resize() {
    size = Math.max(240, Math.min(wrap.clientWidth - 32, 520));
    dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(size * dpr); canvas.height = Math.round(size * dpr);
    canvas.style.width = size + "px"; canvas.style.height = size + "px";
    R = size / 2 - 20; c = size / 2; needsDraw = true;
  }

  function project(latDeg, lonDeg) {
    const p0 = view.lat * RAD, dl = (lonDeg - view.lon) * RAD, la = latDeg * RAD;
    const cl = Math.cos(la), sl = Math.sin(la), cd = Math.cos(dl);
    return {x: c + R * cl * Math.sin(dl),
            y: c - R * (Math.cos(p0) * sl - Math.sin(p0) * cl * cd),
            z: Math.sin(p0) * sl + Math.cos(p0) * cl * cd};   // z > 0 = facing the viewer
  }

  function draw() {
    needsDraw = false;
    view.lon = ((view.lon + 540) % 360) - 180;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);

    const glow = ctx.createRadialGradient(c, c, R * 0.92, c, c, R + 18);
    glow.addColorStop(0, colors.glow); glow.addColorStop(1, transparent(colors.glow));
    ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(c, c, R + 18, 0, 2 * Math.PI); ctx.fill();

    const sea = ctx.createRadialGradient(c - R * 0.35, c - R * 0.4, R * 0.05, c, c, R);
    sea.addColorStop(0, colors.ocean2); sea.addColorStop(1, colors.ocean);
    ctx.fillStyle = sea; ctx.beginPath(); ctx.arc(c, c, R, 0, 2 * Math.PI); ctx.fill();

    // Land: dots get brighter toward the centre of the visible side
    const p0 = view.lat * RAD, l0 = view.lon * RAD, sp = Math.sin(p0), cp = Math.cos(p0);
    const ds = Math.max(1.3, R / 160);
    const bands = [new Path2D(), new Path2D(), new Path2D(), new Path2D()];
    for (let i = 0; i < n; i++) {
      const dl = dLon[i] - l0, cd = Math.cos(dl);
      const z = sp * dSin[i] + cp * dCos[i] * cd;
      if (z <= 0) continue;
      const x = c + R * dCos[i] * Math.sin(dl), y = c - R * (cp * dSin[i] - sp * dCos[i] * cd);
      bands[Math.min(3, (z * 4) | 0)].rect(x - ds / 2, y - ds / 2, ds, ds);
    }
    ctx.fillStyle = colors.land;
    [0.22, 0.42, 0.68, 0.95].forEach((a, b) => { ctx.globalAlpha = a; ctx.fill(bands[b]); });
    ctx.globalAlpha = 1;
    ctx.strokeStyle = colors.rim; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(c, c, R, 0, 2 * Math.PI); ctx.stroke();

    // Pins
    pins = [];
    let label = null;
    regions.forEach(r => {
      const p = project(r.lat, r.lon);
      if (p.z < 0.06) return;
      const count = r.groups.length, rr = 6 + Math.min(7, 2 * Math.sqrt(count - 1));
      const isSel = r.groups.includes(selected);
      ctx.globalAlpha = Math.min(1, p.z * 3);
      if (isSel) {
        ctx.strokeStyle = colors.accent; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(p.x, p.y, rr + 6, 0, 2 * Math.PI); ctx.stroke();
      }
      ctx.fillStyle = colors.accent; ctx.strokeStyle = colors.surface; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(p.x, p.y, rr, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
      if (count > 1) {
        ctx.fillStyle = colors.surface; ctx.font = "600 10px system-ui, sans-serif";
        ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(String(count), p.x, p.y + 0.5);
      }
      ctx.globalAlpha = 1;
      pins.push({r, x: p.x, y: p.y, rr: rr + 5});
      if (isSel) label = {r, p, rr};
    });

    if (label) {   // name tag next to the selected pin, kept inside the canvas
      ctx.font = "600 12px system-ui, sans-serif";
      const text = label.r.name, w = ctx.measureText(text).width + 16, h = 24;
      let lx = label.p.x + label.rr + 10;
      if (lx + w > size - 4) lx = label.p.x - label.rr - 10 - w;
      const ly = Math.max(4, Math.min(size - h - 4, label.p.y - h / 2));
      ctx.fillStyle = colors.surface; ctx.strokeStyle = colors.rim; ctx.lineWidth = 1;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(lx, ly, w, h, 6); else ctx.rect(lx, ly, w, h);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = colors.text; ctx.textAlign = "left"; ctx.textBaseline = "middle";
      ctx.fillText(text, lx + 8, ly + h / 2 + 0.5);
    }
  }

  let last = performance.now();
  function frame(t) {
    const dt = Math.min(64, t - last); last = t;
    if (anim) {
      const k = Math.min(1, (t - anim.t0) / anim.dur), e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      view.lon = anim.lon0 + anim.dlon * e; view.lat = anim.lat0 + anim.dlat * e; needsDraw = true;
      if (k >= 1) anim = null;
    } else if (spinning && !dragging) {
      view.lon += dt * 0.006; needsDraw = true;           // about 6 degrees per second
    }
    if (needsDraw) draw();
    requestAnimationFrame(frame);
  }

  function flyTo(lat, lon) {
    spinning = false;
    const tLat = clampLat(lat), dlon = ((lon - view.lon + 540) % 360) - 180;
    if (reduceMotion) { view.lat = tLat; view.lon += dlon; anim = null; needsDraw = true; return; }
    anim = {t0: performance.now(), dur: 750, lon0: view.lon, lat0: view.lat, dlon, dlat: tLat - view.lat};
  }

  function hitTest(e) {
    const b = canvas.getBoundingClientRect(), x = e.clientX - b.left, y = e.clientY - b.top;
    for (let i = pins.length - 1; i >= 0; i--) {
      const p = pins[i];
      if ((p.x - x) ** 2 + (p.y - y) ** 2 <= p.rr ** 2) return p;
    }
    return null;
  }

  canvas.addEventListener("pointerdown", e => {
    dragging = true; moved = false; anim = null;
    start = {x: e.clientX, y: e.clientY, lon: view.lon, lat: view.lat};
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", e => {
    if (dragging) {
      const dx = e.clientX - start.x, dy = e.clientY - start.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) { moved = true; spinning = false; tip.hidden = true; }
      if (moved) {
        const k = 57.3 / R;                               // one radius dragged = one radian turned
        view.lon = start.lon - dx * k; view.lat = clampLat(start.lat + dy * k); needsDraw = true;
      }
      return;
    }
    const hit = hitTest(e);
    canvas.style.cursor = hit ? "pointer" : "";
    if (!hit) { tip.hidden = true; return; }
    const names = hit.r.groups.map(i => groups[i].name);
    tip.innerHTML = `<b>${esc(hit.r.name)}</b><br><span>${esc(names.slice(0, 4).join(", "))}${names.length > 4 ? ` +${names.length - 4} more` : ""}</span>`;
    const wb = wrap.getBoundingClientRect();
    tip.hidden = false;
    tip.style.left = Math.min(e.clientX - wb.left + 14, wb.width - tip.offsetWidth - 8) + "px";
    tip.style.top = (e.clientY - wb.top + 14) + "px";
  });
  canvas.addEventListener("pointerup", e => {
    if (dragging && !moved) {
      const hit = hitTest(e);
      if (hit) {                                          // repeated clicks cycle through a region's groups
        const gs = hit.r.groups, at = gs.indexOf(selected);
        select(gs[(at + 1) % gs.length], true, true);
      }
    }
    dragging = false;
  });
  canvas.addEventListener("pointercancel", () => { dragging = false; });
  canvas.addEventListener("pointerleave", () => { tip.hidden = true; });
  canvas.addEventListener("keydown", e => {
    const step = {ArrowLeft: [0, -15], ArrowRight: [0, 15], ArrowUp: [10, 0], ArrowDown: [-10, 0]}[e.key];
    if (!step) return;
    e.preventDefault(); spinning = false; anim = null;
    view.lat = clampLat(view.lat + step[0]); view.lon += step[1]; needsDraw = true;
  });

  const portalUrl = id => "https://portal.azure.com/#resource" + id + "/overview";

  function resourcesHtml(g) {
    const tags = g.tags.length
      ? `<div class="chips rg-tags">${g.tags.map(t => `<span class="chip tag">${esc(t)}</span>`).join("")}</div>` : "";
    if (!g.resources.length) return `<div class="rg-res">${tags}<div class="rg-none">No resources in this group.</div></div>`;
    return `<div class="rg-res">${tags}<ul>${g.resources.map(r => `
      <li>${iconHtml(r.icon, 18)}
        <span class="rg-txt"><b title="${esc(r.name)}">${esc(r.name)}</b>
          <span>${esc(r.friendly)}${r.location && r.location !== g.region ? " · " + esc(r.location) : ""}</span></span>
        ${r.id ? `<a class="rg-open" href="${esc(portalUrl(r.id))}" target="_blank" rel="noopener"
                   title="Open in Azure portal" aria-label="Open ${esc(r.name)} in the Azure portal">↗</a>` : ""}
      </li>`).join("")}</ul></div>`;
  }

  function renderList() {
    const q = filterEl.value.trim().toLowerCase();
    const items = groups.map((g, i) => ({g, i})).filter(({g}) =>
      !q || g.name.toLowerCase().includes(q) || String(g.region || "").toLowerCase().includes(q));
    listEl.innerHTML = items.length ? items.map(({g, i}) => {
      const isOpen = i === selected && open;
      return `<div class="rg-group${i === selected ? " on" : ""}${isOpen ? " open" : ""}">
        <button type="button" class="rg-item" data-i="${i}" aria-expanded="${isOpen}">
          <span class="chev" aria-hidden="true">›</span>
          ${iconHtml("rg", 18)}
          <span class="rg-txt"><b>${esc(g.name)}</b>
            <span>${esc(g.region || g.location || "–")}${g.lat == null ? " · not on the map" : ""}${g.current ? ' · <span class="rg-cur">this report</span>' : ""}</span></span>
          <span class="rg-n" title="${plural(g.resources.length, "resource")}">${g.resources.length}</span>
        </button>
        ${isOpen ? resourcesHtml(g) : ""}
      </div>`;
    }).join("")
      : `<div class="empty">No resource group matches “${esc(q)}”.</div>`;
  }

  function select(i, fly, reveal) {
    selected = i; open = true;
    renderList();
    const g = groups[i];
    if (fly && g && g.lat != null) flyTo(g.lat, g.lon);
    if (reveal) {
      const item = listEl.querySelector(".rg-group.open");
      if (item) listEl.scrollTo({top: item.offsetTop - listEl.offsetTop - 4, behavior: reduceMotion ? "auto" : "smooth"});
    }
    needsDraw = true;
  }

  listEl.addEventListener("click", e => {
    const b = e.target.closest(".rg-item");
    if (!b) return;
    const i = Number(b.dataset.i);
    if (i === selected && open) { open = false; renderList(); }   // second click closes the group
    else select(i, true, false);
  });
  filterEl.addEventListener("input", renderList);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", readColors);
  new ResizeObserver(resize).observe(wrap);

  readColors(); resize();
  if (first >= 0) select(first, false, false); else renderList();
  requestAnimationFrame(frame);
})();
"""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resource-group", default="rg-sentinel-lab")
    p.add_argument("--workspace", default="log-sentinel-lab")
    p.add_argument("--out", default=os.path.join(SCRIPT_DIR, "..", "reports", "rg-report.html"))
    a = p.parse_args()

    print("Reading account ...")
    account = az("account", "show") or {}
    sub_id = account.get("id", "")
    sub_name = account.get("name", "")

    print(f"Reading resource group {a.resource_group} ...")
    rg = az("group", "show", "--name", a.resource_group) or {}

    print("Reading all resource groups and resources in the subscription ...")
    all_groups = az("group", "list") or []
    all_resources = az("resource", "list") or []
    resources = [r for r in all_resources if (r.get("resourceGroup") or "").lower() == a.resource_group.lower()]

    print("Reading Azure region coordinates ...")
    locations = az("account", "list-locations") or []

    ws_id = f"/subscriptions/{sub_id}/resourceGroups/{a.resource_group}/providers/Microsoft.OperationalInsights/workspaces/{a.workspace}"

    print("Reading Sentinel analytics rules ...")
    rules = az_get(f"{ARM}{ws_id}/providers/Microsoft.SecurityInsights/alertRules?api-version=2024-03-01") or []

    print("Reading Sentinel automation rules ...")
    autorules = az_get(f"{ARM}{ws_id}/providers/Microsoft.SecurityInsights/automationRules?api-version=2024-03-01") or []

    print("Reading recent incidents ...")
    incidents = az_get(
        f"{ARM}{ws_id}/providers/Microsoft.SecurityInsights/incidents?api-version=2024-03-01"
        "&$orderby=properties/createdTimeUtc desc&$top=15"
    ) or []

    print("Reading data sources (diagnostic settings) ...")
    sub_diag = az_get(f"{ARM}/subscriptions/{sub_id}/providers/Microsoft.Insights/diagnosticSettings?api-version=2021-05-01-preview") or []
    entra_diag = az_get(f"{ARM}/providers/microsoft.aadiam/diagnosticSettings?api-version=2017-04-01") or []

    print("Building the world map ...")
    world = world_data(all_groups, all_resources, locations, a.resource_group)

    page = render(a, sub_name, rg, resources, rules, autorules, incidents, sub_diag, entra_diag, world)

    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"\nReport written to {out}")


def render(a, sub_name, rg, resources, rules, autorules, incidents, sub_diag, entra_diag, world):
    # ---- resources -----------------------------------------------------
    res_rows = []
    for r in sorted(resources, key=lambda r: (r.get("type", "").lower(), r.get("name", ""))):
        rtype = r.get("type", "")
        friendly, key = resource_kind(r)
        tags = [f"{k}={v}" for k, v in (r.get("tags") or {}).items()]
        res_rows.append([
            name_cell(key, r.get("name"), rtype),
            esc(friendly),
            esc(r.get("location")),
            chips(tags, "tag") if tags else '<span class="muted">–</span>',
        ])

    # ---- data sources --------------------------------------------------
    flows = []
    for items, scope, key in ((sub_diag, "Subscription Activity Log", "activity"), (entra_diag, "Microsoft Entra ID tenant", "tenant")):
        for d in items:
            pr = d.get("properties", {})
            cats = [l.get("category") for l in pr.get("logs", []) if l.get("enabled")]
            target = (pr.get("workspaceId") or "").rsplit("/", 1)[-1]
            flows.append(f"""<div class="flow">
  <div>{name_cell(key, d.get("name"), scope)}</div>
  <div class="arrow" aria-hidden="true">→</div>
  <div>{name_cell("law", target or "–", "workspace")}</div>
  <div><div class="lbl">Log categories</div>{chips(cats) if cats else '<span class="muted">none enabled</span>'}</div>
</div>""")
    src_html = f'<div class="flows">{"".join(flows)}</div>' if flows else '<div class="empty">No diagnostic settings found.</div>'

    # ---- analytics rules -----------------------------------------------
    rule_rows = []
    for r in sorted(rules, key=lambda r: r.get("properties", {}).get("displayName", "")):
        pr = r.get("properties", {})
        kind = r.get("kind", "")
        rule_rows.append([
            name_cell("sentinel", pr.get("displayName"), kind),
            sev(pr.get("severity", "")),
            pill("Enabled", "ok") if pr.get("enabled") else pill("Disabled", "off"),
            chips([split_camel(t) for t in pr.get("tactics") or []]) if pr.get("tactics") else '<span class="muted">–</span>',
            technique_links(pr.get("techniques")),
            esc(iso_duration(pr.get("queryFrequency", ""))) or '<span class="muted">–</span>',
        ])

    # ---- automation rules ----------------------------------------------
    auto_rows = []
    for r in autorules:
        pr = r.get("properties", {})
        logic = pr.get("triggeringLogic") or {}
        trig = f'{split_camel(logic.get("triggersOn", ""))} {split_camel(logic.get("triggersWhen", "")).lower()}'.strip()
        actions = [split_camel(x.get("actionType", "")) for x in pr.get("actions", [])]
        auto_rows.append([
            name_cell("logic", pr.get("displayName"), f'order {pr.get("order")}' if pr.get("order") is not None else ""),
            esc(trig or "–"),
            chips(actions) if actions else '<span class="muted">–</span>',
            pill("Enabled", "ok") if logic.get("isEnabled") else pill("Disabled", "off"),
        ])

    # ---- incidents -----------------------------------------------------
    inc_rows = []
    for i in incidents:
        pr = i.get("properties", {})
        created = (pr.get("createdTimeUtc") or "")[:16].replace("T", " ")
        status = pr.get("status", "")
        inc_rows.append([
            f'<span class="num">#{esc(pr.get("incidentNumber"))}</span>',
            f'<b>{esc(pr.get("title"))}</b>',
            sev(pr.get("severity", "")),
            pill(status, STATUS_KIND.get(status, "")),
            f'<span class="when">{esc(created)}</span>',
        ])

    # ---- stats ---------------------------------------------------------
    open_inc = [i for i in incidents if i.get("properties", {}).get("status") != "Closed"]
    by_sev = {}
    for i in open_inc:
        s = i.get("properties", {}).get("severity", "Unknown")
        by_sev[s] = by_sev.get(s, 0) + 1
    sev_order = ["High", "Medium", "Low", "Informational"]
    sev_summary = " · ".join(f"{by_sev[s]} {s}" for s in sev_order if s in by_sev) or "none open"
    enabled_rules = sum(1 for r in rules if r.get("properties", {}).get("enabled"))

    stats = [
        ("rg", len(resources), "Resources", f"in {a.resource_group}", ""),
        ("sentinel", len(rules), "Analytics rules", f"{enabled_rules} enabled", ""),
        ("diag", len(flows), "Data sources", "diagnostic settings", ""),
        ("alerts", len(open_inc), "Open incidents", f"{sev_summary} (latest {len(incidents)})",
         "alert" if by_sev.get("High") else ""),
    ]
    stat_html = "".join(
        f'<div class="stat {cls}">{icon(k, 32)}<div><div class="n">{n}</div>'
        f'<div class="l">{esc(l)}</div><div class="s">{esc(s)}</div></div></div>'
        for k, n, l, s, cls in stats
    )

    def section(sid, title, count, body, hint=""):
        hint_html = f'<span class="hint">{esc(hint)}</span>' if hint else ""
        return (f'<section id="{sid}"><div class="sh"><h2>{esc(title)}</h2>'
                f'<span class="count">{count}</span>{hint_html}</div>{body}</section>')

    # ---- world map -----------------------------------------------------
    wg = world["groups"]
    n_regions = len({g["location"] for g in wg if g["lat"] is not None})
    world_json = json.dumps(world, separators=(",", ":")).replace("</", "<\\/")
    world_html = f"""<div class="world">
  <div class="globe-wrap">
    <canvas id="globe" tabindex="0" role="img"
      aria-label="Globe with one pin per Azure region that holds resource groups. Drag or use the arrow keys to rotate."></canvas>
    <div id="globe-tip" class="globe-tip" hidden></div>
    <div class="globe-hint">Drag or use the arrow keys to rotate · click a pin to open its resource group</div>
  </div>
  <div class="rg-panel">
    <input id="rg-filter" type="search" placeholder="Filter by name or region" aria-label="Filter resource groups">
    <div id="rg-list" class="rg-list"></div>
  </div>
</div>
<script type="application/json" id="world-data">{world_json}</script>
<script>{WORLD_JS}</script>"""

    logo, favicon = file_uri(LOGO_FILE), file_uri(FAVICON_FILE)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(a.resource_group)} · Sentinel Lab</title>
{f'<link rel="icon" type="image/svg+xml" href="{favicon}">' if favicon else ""}
<style>{CSS}</style></head>
<body>
<header class="top"><div class="wrap">
  <div class="hero">
    {f'<img class="brand" src="{logo}" width="48" height="48" alt="Sentinel Lab logo">' if logo else icon("rg", 44, "ic-lg")}
    <div><div class="eyebrow">Sentinel Lab · Azure resource group report</div><h1>{esc(a.resource_group)}</h1></div>
  </div>
  <div class="meta">
    <span>{icon("sub", 14)}Subscription <b>{esc(sub_name or "–")}</b></span>
    <span>Location <b>{esc(rg.get("location") or "–")}</b></span>
    <span>{icon("sentinel", 14)}Workspace <b>{esc(a.workspace)}</b></span>
    <span>Generated <b>{esc(now)}</b></span>
  </div>
  <nav class="toc" aria-label="Sections">
    <a href="#world">World map</a><a href="#resources">Resources</a><a href="#sources">Data sources</a><a href="#rules">Analytics rules</a>
    <a href="#automation">Automation</a><a href="#incidents">Incidents</a>
  </nav>
</div></header>

<div class="wrap"><main>
<div class="stats">{stat_html}</div>

{section("world", "Resource groups worldwide", len(wg), world_html, f"{len(wg)} resource group{'s' if len(wg) != 1 else ''} in {n_regions} region{'s' if n_regions != 1 else ''} · whole subscription")}

{section("resources", "Resources", len(res_rows), table(["Resource", "Type", "Location", "Tags"], res_rows, "No resources found."))}

{section("sources", "Data sources", len(flows), src_html, "Diagnostic settings that send logs to Sentinel")}

{section("rules", "Sentinel analytics rules", len(rule_rows), table(["Rule", "Severity", "Status", "Tactics", "MITRE techniques", "Runs every"], rule_rows, "No analytics rules found."))}

{section("automation", "Automation rules", len(auto_rows), table(["Rule", "Trigger", "Actions", "Status"], auto_rows, "No automation rules found."))}

{section("incidents", "Latest incidents", len(inc_rows), table(["#", "Title", "Severity", "Status", "Created (UTC)"], inc_rows, "No incidents yet."), "Newest first, up to 15")}
</main>

<footer>
  <span>Generated by sentinel-lab/scripts/rg_report.py with read-only Azure Resource Manager calls. Local report, do not commit.</span>
  <span>Icons: Microsoft Azure Architecture Icons · Map: Natural Earth</span>
</footer>
</div>
</body></html>"""


if __name__ == "__main__":
    main()
