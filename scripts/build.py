#!/usr/bin/env python3
"""Draws the live profile widgets from the public contribution calendar.

    GH_TOKEN=... python3 scripts/build.py dist

Writes stats.svg, activity.svg and opg.svg into the output directory.
Standard library only, so it runs anywhere Python 3 does.
"""
import datetime as dt
import json
import math
import os
import sys
import urllib.request

LOGIN = os.environ.get("PROFILE_LOGIN", "IbraAFK")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""

BG, PANE, RULE, RULE2 = "#0c1116", "#07090c", "#293139", "#1e262e"
INK, DIM, FAINT = "#e7ebef", "#8d98a3", "#616b75"
TEAL, GREEN, AMBER, RED = "#5ecfc6", "#71c176", "#d3a63f", "#e5827a"
SANS = '-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif'
MONO = 'ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace'
STYLE = (
    f".sans{{font-family:{SANS}}}.mono{{font-family:{MONO}}}"
    f".ink{{fill:{INK}}}.dim{{fill:{DIM}}}.faint{{fill:{FAINT}}}"
    f".teal{{fill:{TEAL}}}.green{{fill:{GREEN}}}.amber{{fill:{AMBER}}}.red{{fill:{RED}}}"
    ".pulse{animation:pulse 2.4s ease-in-out infinite}"
    "@keyframes pulse{0%,100%{opacity:.3}50%{opacity:1}}"
    "@media (prefers-reduced-motion:reduce){.pulse{animation:none}}"
)

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch():
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-vitals"},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        payload = json.load(res)
    if payload.get("errors"):
        raise SystemExit(f"GitHub API error: {payload['errors']}")
    cal = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [
        (dt.date.fromisoformat(d["date"]), d["contributionCount"])
        for w in cal["weeks"]
        for d in w["contributionDays"]
    ]
    days.sort()
    return cal["totalContributions"], days


def day(d):
    return f"{d.day} {d:%b}"


def num(n):
    return f"{n:,}"


def streaks(days):
    """Current and longest runs of consecutive days with a contribution."""
    longest = (0, None, None)
    run, start = 0, None
    for date, count in days:
        if count:
            if not run:
                start = date
            run += 1
            if run > longest[0]:
                longest = (run, start, date)
        else:
            run = 0
    # Today may simply not have happened yet, so an empty today does not break the run.
    tail = days[:-1] if days and days[-1][1] == 0 else days
    current = 0
    for _, count in reversed(tail):
        if not count:
            break
        current += 1
    return current, longest


def svg(width, height, label, body, extra_style="", defs=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-label="{label}">'
        f"<defs>{defs}</defs><style>{STYLE}{extra_style}</style>{body}</svg>\n"
    )


# ── stat tiles ────────────────────────────────────────────────────────────────

def draw_stats(total, days):
    current, (longest, lstart, lend) = streaks(days)
    best_date, best = max(days, key=lambda x: x[1])
    average = total / max(len(days), 1)
    tiles = [
        ("CONTRIBUTIONS · 12 MO", num(total), "teal", f"dose: {average:.1f} a day"),
        ("CURRENT STREAK", f"{current}", "green",
         "no dry socket so far" if current else "healing. back soon."),
        ("LONGEST STREAK", f"{longest}", "amber",
         f"{day(lstart)} → {day(lend)}" if longest else "nothing yet"),
        ("BUSIEST DAY", num(best), "red", f"{day(best_date)} · needed a nap"),
    ]
    units = ["", "days", "days", ""]
    out = []
    for i, ((label, value, colour, caption), unit) in enumerate(zip(tiles, units)):
        x = i * 214
        out.append(
            f'<g transform="translate({x} 0)">'
            f'<rect x=".5" y=".5" width="197" height="139" rx="12" fill="{BG}" stroke="{RULE2}"/>'
            f'<text x="18" y="32" class="mono dim" font-size="10" letter-spacing="1.1">{label}</text>'
            f'<text x="17" y="86" class="sans {colour}" font-size="40" font-weight="700" letter-spacing="-1">{value}'
            + (f'<tspan class="mono dim" font-size="12" font-weight="400" letter-spacing="0" dx="7">{unit}</tspan>' if unit else "")
            + "</text>"
            f'<text x="18" y="116" class="mono faint" font-size="10.500">{caption}</text>'
            "</g>"
        )
    label = (
        f"{num(total)} contributions in the last year, current streak {current} days, "
        f"longest streak {longest} days, busiest day {num(best)} contributions"
    )
    return svg(840, 140, label, "".join(out))


# ── activity trace ────────────────────────────────────────────────────────────

def draw_activity(days, span=60):
    recent = days[-span:]
    counts = [c for _, c in recent]
    top = max(max(counts), 1)
    x0, x1, y0, y1 = 56, 812, 52, 168
    step = (x1 - x0) / (len(recent) - 1)

    # Log scale: one enormous day would otherwise flatten every ordinary one.
    def level(c):
        return math.log10(1 + c) / math.log10(1 + top)

    pts = [(x0 + i * step, y1 - level(c) * (y1 - y0)) for i, c in enumerate(counts)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"M{x0},{y1} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f" L{x1},{y1} Z"
    median = sorted(counts)[len(counts) // 2]
    ticks = [0] + [t for t in (10, 100, 1000, 10000) if t <= top]
    grid = "".join(
        f'<path d="M{x0} {y1 - level(t) * (y1 - y0):.1f}H{x1}" stroke="{RULE2}" stroke-width="1"/>'
        f'<text x="{x0 - 8}" y="{y1 - level(t) * (y1 - y0) + 3.5:.1f}" text-anchor="end" '
        f'class="mono faint" font-size="9.500">{num(t)}</text>'
        for t in ticks
    )
    mid = recent[len(recent) // 2][0]
    lx, ly = pts[-1]
    defs = (
        f'<linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{GREEN}" stop-opacity=".32"/>'
        f'<stop offset="1" stop-color="{GREEN}" stop-opacity="0"/></linearGradient>'
        f'<clipPath id="reveal"><rect x="{x0 - 4}" y="{y0 - 12}" height="{y1 - y0 + 16}" width="{x1 - x0 + 8}">'
        f'<animate attributeName="width" dur="14s" repeatCount="indefinite" '
        f'values="0;{x1 - x0 + 8};{x1 - x0 + 8}" keyTimes="0;.28;1"/></rect></clipPath>'
        '<filter id="glow" x="-10%" y="-40%" width="120%" height="180%">'
        '<feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/>'
        '<feMergeNode in="SourceGraphic"/></feMerge></filter>'
    )
    body = (
        f'<rect x=".5" y=".5" width="839" height="209" rx="12" fill="{BG}" stroke="{RULE2}"/>'
        f'<text x="24" y="30" class="mono dim" font-size="10" letter-spacing="1.1">ACTIVITY · LAST {len(recent)} DAYS</text>'
        f'<text x="816" y="30" text-anchor="end" class="mono dim" font-size="10.500">'
        f'rhythm: sinus-ish · median <tspan class="green">{median}</tspan> a day · peak {num(top)} · log scale</text>'
        f"{grid}"
        f'<g clip-path="url(#reveal)">'
        f'<path d="{area}" fill="url(#fill)"/>'
        f'<polyline points="{line}" fill="none" stroke="{GREEN}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round" filter="url(#glow)"/>'
        f'<circle class="pulse" cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="{GREEN}"/>'
        "</g>"
        f'<text x="{x0}" y="190" class="mono faint" font-size="9.500">{day(recent[0][0])}</text>'
        f'<text x="{(x0 + x1) / 2}" y="190" text-anchor="middle" class="mono faint" font-size="9.500">{day(mid)}</text>'
        f'<text x="{x1}" y="190" text-anchor="end" class="mono faint" font-size="9.500">today</text>'
    )
    label = (f"Daily contributions over the last {len(recent)} days on a log scale: "
             f"median {median} a day, peak {num(top)}")
    return svg(840, 210, label, body, defs=defs)


# ── the last four weeks as a panoramic radiograph ─────────────────────────────
#
# 28 teeth, one per day, charted the way teeth are counted: 17→27 along the top,
# then 37→47 along the bottom, so today is always the lower right second molar.
# The work done that day shows up as dental work on that tooth. The wisdom teeth
# carry no data. They are impacted, as is tradition.
#
# Everything is drawn around the midline (x = 0) and the occlusal plane (y = 0).
# Tooth art is drawn crown-up with the mesial side on the left (negative x).

DENTINE, ENAMEL, PULP, METAL = "#a3afba", "#e6ecf0", "#3d4954", "#ffffff"

MOLAR_TOP = ("M-19 30C-24 24-25 12-21 5C-18 0-13-1-10 3C-7 6-4 6-1 3C2-1 8-1 11 3"
             "C13 6 15 5 17 3C20 0 23 4 23 10C24 18 22 25 19 30")
MOLAR_DENTINE = "M-16 30C-19 22-19 13-16 9C-12 6-6 10 0 9C6 10 13 6 17 10C20 16 18 24 16 30Z"
MOLAR_FILL = ["M-6 4C-6 10-3 13 0 13C4 13 7 10 7 4C3 6-2 6-6 4Z",
              "M-22 7C-18 1-13 0-10 3C-7 6-4 6-1 3C2-1 8-1 11 3C13 6 15 5 17 3C20 1 23 5 23 10"
              "L23 17L15 17C15 13 14 11 12 11L-10 11C-13 11-14 14-14 18L-23 18C-24 13-24 10-22 7Z"]

TEETH = {
    "lower_molar": dict(
        span=49, top=MOLAR_TOP, close="C10 27-10 27-19 30Z", dentine=MOLAR_DENTINE, fills=MOLAR_FILL,
        roots="C20 38 21 50 19 64C18 74 15 81 12 81C9 81 8 72 7 62C6 50 4 42 0 40"
              "C-4 42-6 52-7 64C-8 76-11 84-14 84C-18 84-20 72-21 60C-22 48-21 38-19 30Z",
        pulp="M-10 26C-11 20-8 17-5 19C-2 21 2 21 5 19C8 17 12 20 11 26C11 32 13 40 14 52"
             "C15 62 14 72 12.5 76L11.5 76C11.5 66 10 50 7 38C5 33 3 32 0 32C-3 32-5 33-7 38"
             "C-10 50-13 64-14 78L-15 78C-16 66-15 50-13 40C-11 34-10 30-10 26Z",
        canals=["M-9 31C-12 45-14.5 62-14.5 77", "M9 31C12 44 13.5 60 12 75"], apex=84, neck=30),
    "upper_molar": dict(
        span=49, top=MOLAR_TOP, close="C10 27-10 27-19 30Z", dentine=MOLAR_DENTINE, fills=MOLAR_FILL,
        roots="C20 38 20 48 17 58C15 66 12 70 10 68C8 66 8 56 7 48C6 42 3 38 0 38"
              "C-3 38-6 42-7 50C-8 60-10 72-13 72C-17 72-20 60-21 50C-22 42-21 36-19 30Z",
        behind="M-9 34C-10 50-6 70 0 78C6 70 10 50 9 34Z",
        pulp="M-10 26C-11 20-8 17-5 19C-2 21 2 21 5 19C8 17 12 20 11 26C11 32 12 40 12 50"
             "C12 56 11 62 10.5 64L9.5 64C9.5 56 9 46 7 38C5 33 3 32 0 32C-3 32-5 33-7 38"
             "C-9 46-11 58-12.5 67L-13.5 67C-14 58-14 46-13 40C-11 34-10 30-10 26Z",
        canals=["M-9 31C-11 42-13 56-13 66", "M9 31C11 40 11 54 10 63", "M0 33C-1 48 0 62 0 72"],
        apex=78, neck=30),
    "premolar": dict(
        span=32, top="M-11 30C-15 24-16 13-12 7C-9 2-3 0 0-3C3 0 9 2 12 7C16 13 15 24 11 30",
        close="C5 28-5 28-11 30Z", dentine="M-9 30C-12 23-12 15-9 10C-6 6-3 5 0 3C3 5 6 6 9 10C12 15 12 23 9 30Z",
        roots="C12 42 10 62 5 80C3 87-3 87-5 80C-10 62-12 42-11 30Z",
        pulp="M-4 22C-4 16-2 12 0 10C2 12 4 16 4 22C4 40 3 60 1 78L-1 78C-3 60-4 40-4 22Z",
        fills=["M-5 3C-5 9-2 11 0 11C3 11 5 9 5 3C2-1-2-1-5 3Z",
               "M-13 9C-9 3-3 1 0-2C3 1 9 3 13 9L14 17L8 17C8 13 7 11 5 11L-5 11C-7 11-8 13-8 17L-14 17Z"],
        canals=["M0 24C0 45 0 62 0 78"], apex=86, neck=30),
    "canine": dict(
        span=32, top="M-11 36C-16 28-16 16-11 9C-7 4-3 1 0-4C3 1 7 4 11 9C16 16 16 28 11 36",
        close="C5 34-5 34-11 36Z", dentine="M-9 36C-13 28-12 18-8 13C-5 9-2 6 0 2C2 6 5 9 8 13C12 18 13 28 9 36Z",
        roots="C12 52 10 80 5 100C3 108-3 108-5 100C-10 80-12 52-11 36Z",
        pulp="M-3.5 28C-3.5 20-1.5 14 0 10C1.5 14 3.5 20 3.5 28C3.5 50 3 78 1 98L-1 98C-3 78-3.5 50-3.5 28Z",
        fills=["M7 12C11 14 13 18 12 22C9 22 6 19 6 15Z",
               "M7 10C12 13 14 20 12 26C8 25 5 20 5 14ZM-7 10C-12 13-14 20-12 26C-8 25-5 20-5 14Z"],
        canals=["M0 28C0 55 0 80 0 98"], apex=106, neck=36),
    "incisor": dict(
        span=36, top="M-12 40C-16 30-18 14-17 4C-17 1-15 0-12 0L13 0C16 0 18 2 18 5C18 16 16 30 12 40",
        close="C5 37-5 37-12 40Z", dentine="M-10 40C-13 30-14 16-13 8C-8 6 8 6 13 8C14 16 13 30 10 40Z",
        roots="C12 55 9 80 4 94C2 99-2 99-4 94C-9 80-12 55-12 40Z",
        pulp="M-5 12C-3 14 3 14 5 12C5 24 4 34 3 44C3 60 2 80 .8 92L-.8 92C-2 80-3 60-3 44C-4 34-5 24-5 12Z",
        fills=["M10 0L13 0C16 0 18 2 18 5C18 9 17.5 12 17 15C13 14 10 10 10 5Z",
               "M10 0L13 0C16 0 18 2 18 5C18 9 17.5 12 17 15C13 14 10 10 10 5Z"
               "M-9 0L-12 0C-15 0-17 1-17 4C-17 8-16.5 12-16 15C-12 14-9 10-9 5Z"],
        canals=["M0 30C0 55 0 78 0 92"], apex=97, neck=40),
}

# Midline outwards: (kind, width, length scale).
UPPER = [("incisor", 37, 1), ("incisor", 29, .92), ("canine", 33, 1), ("premolar", 31, 1),
         ("premolar", 29, 1), ("upper_molar", 44, 1), ("upper_molar", 40, 1)]
LOWER = [("incisor", 22, .85), ("incisor", 24, .85), ("canine", 30, .95), ("premolar", 31, 1),
         ("premolar", 32, 1), ("lower_molar", 48, 1), ("lower_molar", 46, 1)]
SMILE, HALF = 24, 243


def curve(x):
    """Height of the occlusal plane at x, and its slope in degrees."""
    return -SMILE * (x / HALF) ** 2, math.degrees(math.atan(-2 * SMILE * x / HALF ** 2))


def seats():
    """The 28 teeth in charting order as (kind, x, y, transform)."""
    def half(spec, side, upper):
        out, edge = [], 0
        for kind, w, sy in spec:
            x = side * (edge + w / 2)
            edge += w
            dy, slope = curve(x)
            sx = w / TEETH[kind]["span"] * (1 if side > 0 else -1)
            if upper:
                y, turn, sy = dy - 1.5, -.5 * slope, -sy
            else:
                y, turn = dy + 1.5, slope
            out.append((kind, x, y, f"translate({x:.1f} {y:.1f}) rotate({turn:.1f}) scale({sx:.3f} {sy:.3f})"))
        return out

    ur, ul = half(UPPER, -1, True), half(UPPER, 1, True)
    ll, lr = half(LOWER, 1, False), half(LOWER, -1, False)
    return ur[::-1] + ul + ll[::-1] + lr


def tooth_art(kind):
    t = TEETH[kind]
    behind = f'<path d="{t["behind"]}" fill="{DENTINE}" opacity=".5"/>' if "behind" in t else ""
    return (
        behind
        + f'<path d="{t["top"]}{t["roots"]}" fill="{DENTINE}" stroke="#05070a" stroke-opacity=".75" '
          f'stroke-width="2.4" paint-order="stroke"/>'
        + f'<path d="{t["top"]}{t["close"]}" fill="{ENAMEL}"/>'
        + f'<path d="{t["dentine"]}" fill="{DENTINE}"/>'
        + f'<path d="{t["pulp"]}" fill="{PULP}"/>'
    )


def implant(kind):
    t = TEETH[kind]
    top, tip = t["neck"] + 7, t["neck"] + 58
    left, right = [], []
    steps = 9
    for i in range(steps + 1):
        y = top + (tip - top) * i / steps
        half = 5.6 - 2.0 * i / steps
        bite = 1.5 if i % 2 else 0
        left.append((-(half + bite), y))
        right.append((half + bite, y))
    pts = left + [(0, tip + 4)] + right[::-1]
    screw = "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z"
    return (
        f'<path d="{screw}" fill="{METAL}"/>'
        f'<path d="M-6 {t["neck"] - 3}L6 {t["neck"] - 3}L4.5 {top}L-4.5 {top}Z" fill="{METAL}"/>'
        f'<path d="{t["top"]}{t["close"]}" fill="{METAL}" stroke="{AMBER}" stroke-width="1.6"/>'
    )


def dental_work(kind, level):
    """0 sound, 1 filling, 2 large filling, 3 large filling and root filling, 4 crown and root filling."""
    t = TEETH[kind]
    if level == 0:
        return ""
    if level <= 2:
        return f'<path d="{t["fills"][level - 1]}" fill="{METAL}"/>'
    canals = "".join(
        f'<path d="{c}" fill="none" stroke="{METAL}" stroke-width="2.4" stroke-linecap="round"/>'
        for c in t["canals"])
    if level == 3:
        return f'<path d="{t["fills"][1]}" fill="{METAL}"/>' + canals
    return f'<path d="{t["top"]}{t["close"]}" fill="{METAL}"/>' + canals


def mirror_path(segments):
    """Close a left-half outline (midline to midline) with its mirror image."""
    d = f"M{segments[0][0][0]} {segments[0][0][1]}"
    for _, c1, c2, p in segments:
        d += f"C{c1[0]} {c1[1]} {c2[0]} {c2[1]} {p[0]} {p[1]}"
    for p0, c1, c2, _ in reversed(segments):
        d += f"C{-c2[0]} {c2[1]} {-c1[0]} {c1[1]} {-p0[0]} {p0[1]}"
    return d + "Z"


def both(markup):
    """Draw something on the image's left and again mirrored on its right."""
    return f'{markup}<g transform="scale(-1 1)">{markup}</g>'


MANDIBLE = [
    ((0, 36), (-80, 36), (-160, 30), (-232, 14)),            # alveolar crest
    ((-232, 14), (-252, 8), (-268, -8), (-276, -30)),        # external oblique ridge
    ((-276, -30), (-284, -62), (-286, -96), (-290, -116)),   # anterior ramus to coronoid tip
    ((-290, -116), (-297, -112), (-302, -86), (-316, -84)),  # sigmoid notch
    ((-316, -84), (-328, -82), (-334, -100), (-338, -110)),  # condylar neck
    ((-338, -110), (-340, -128), (-372, -128), (-372, -108)),  # condylar head
    ((-372, -108), (-372, -60), (-368, 40), (-354, 96)),     # posterior border of ramus
    ((-354, 96), (-350, 112), (-338, 126), (-318, 132)),     # angle
    ((-318, 132), (-220, 166), (-100, 184), (0, 184)),       # inferior border to the chin
]
CANAL = "M-330 -36C-324 40-292 96-220 104C-170 110-130 112-108 98"


def anatomy():
    jaw = mirror_path(MANDIBLE)
    bone, cortex, line = "#2c3741", "#8e9ba7", "#7d8b97"
    sinus = ("M-284-240L-98-240L-100-140C-98-118-120-104-150-100C-170-97-180-106-200-100"
             "C-230-92-260-100-272-112C-280-122-284-140-284-240Z")
    sinus_floor = "M-274-116C-262-100-230-92-200-100C-180-106-170-97-150-100C-125-103-108-112-102-128"
    nose = ("M-58-190C-62-150-60-124-40-116C-20-110-8-112 0-116C8-112 20-110 40-116"
            "C60-124 62-150 58-190Z")
    return (
        # soft tissue haze and the ghost of the cervical spine
        '<ellipse cx="0" cy="-10" rx="390" ry="180" fill="#10161c" filter="url(#haze)"/>'
        '<ellipse cx="0" cy="70" rx="58" ry="210" fill="#9aa7b3" opacity=".07" filter="url(#haze)"/>'
        # maxilla: body, alveolar process, sinuses, nasal cavity, palate, zygomatic buttress
        '<path d="M-296-240L296-240L290-70C200-46 100-37 0-37C-100-37-200-46-290-70Z" fill="#1d2730" filter="url(#blur3)"/>'
        f'<path d="M-270-66C-200-46-100-37 0-37C100-37 200-46 270-66C292-74 296-104 286-124C200-138 100-140 0-140'
        f'C-100-140-200-138-286-124C-296-104-292-74-270-66Z" fill="{bone}" filter="url(#blur2)"/>'
        + both(f'<path d="{sinus}" fill="#05080b" opacity=".55" filter="url(#blur2)"/>'
               f'<path d="{sinus_floor}" fill="none" stroke="{line}" stroke-opacity=".55" stroke-width="1.4" filter="url(#blur1)"/>')
        + f'<path d="{nose}" fill="#05080b" opacity=".5" filter="url(#blur2)"/>'
        + f'<path d="M2-190C-3-160 5-134 0-116" fill="none" stroke="{line}" stroke-width="2.4" opacity=".5" filter="url(#blur1)"/>'
        f'<path d="M-9-113L0-119L9-113" fill="none" stroke="{cortex}" stroke-width="2" opacity=".7"/>'
        f'<path d="M-300-118C-200-108-80-112 0-114C80-112 200-108 300-118" fill="none" stroke="{cortex}" '
        f'stroke-width="3.2" opacity=".5" filter="url(#blur1)"/>'
        f'<path d="M-296-127C-200-117-80-121 0-123C80-121 200-117 296-127" fill="none" stroke="{cortex}" '
        f'stroke-width="2" opacity=".25" filter="url(#blur1)"/>'
        + both(f'<path d="M-216-190C-216-152-200-132-181-132C-163-132-150-152-150-190" fill="none" '
               f'stroke="{cortex}" stroke-width="3" opacity=".28" filter="url(#blur2)"/>')
        # glenoid fossa and articular eminence over each condyle
        + both(f'<path d="M-392-112C-386-142-352-146-336-128C-327-117-318-118-304-126" fill="none" '
               f'stroke="{cortex}" stroke-width="3" opacity=".3" filter="url(#blur2)"/>')
        # mandible: bone, trabecular texture, cortex
        + f'<path d="{jaw}" fill="url(#density)" filter="url(#blur1)"/>'
        f'<path d="{jaw}" fill="#fff" filter="url(#trabeculae)" opacity=".16"/>'
        + both(f'<path d="M-372-108C-372-60-368 40-354 96C-350 112-338 126-318 132" fill="none" '
               f'stroke="{cortex}" stroke-width="3.5" opacity=".6" filter="url(#blur1)"/>')
        + f'<path d="M-318 132C-220 166-100 184 0 184C100 184 220 166 318 132" fill="none" stroke="{cortex}" '
          f'stroke-width="8" opacity=".8" stroke-linecap="round" filter="url(#blur2)"/>'
        + both(f'<path d="M-276-30C-268-8-252 8-232 14" fill="none" stroke="{cortex}" stroke-width="3" '
               f'opacity=".4" filter="url(#blur1)"/>')
        # inferior alveolar canals and mental foramina
        + both(f'<path d="{CANAL}" fill="none" stroke="{cortex}" stroke-width="8" opacity=".22"/>'
               f'<path d="{CANAL}" fill="none" stroke="#141c23" stroke-width="5.6" opacity=".7" filter="url(#crisp)"/>'
               '<ellipse cx="-108" cy="97" rx="4.5" ry="3.6" fill="#141c23" opacity=".7"/>')
    )


def wisdom_teeth():
    lower, upper = tooth_art("lower_molar"), tooth_art("upper_molar")
    return (
        # 48 mesioangular with its roots across the canal; 38 horizontal against the 37
        f'<g transform="translate(-244 4) rotate(40) scale(-.9 .9)">{lower}</g>'
        f'<g transform="translate(240 38) rotate(-85) scale(.9 .9)">{lower}</g>'
        # 18 and 28 unerupted and distoangular, up in the tuberosities
        f'<g transform="translate(-270 -62) rotate(18) scale(-.78 -.78)">{upper}</g>'
        f'<g transform="translate(270 -62) rotate(-18) scale(.78 -.78)">{upper}</g>'
    )


def draw_opg(days):
    recent = days[-28:]
    counts = [c for _, c in recent]
    best = max(range(28), key=lambda i: counts[i])
    rest = sorted(c for i, c in enumerate(counts) if c and i != best)
    cuts = [rest[len(rest) * k // 4] for k in (1, 2, 3)] if len(rest) >= 4 else [10 ** 9] * 3

    def level(i):
        c = counts[i]
        if not c:
            return 0
        return 1 + sum(c >= cut for cut in cuts)

    teeth, work, notes = [], [], []
    for i, (kind, x, y, place) in enumerate(seats()):
        upper = i < 14
        apex = TEETH[kind]["apex"] * (1 if not upper else -1)
        if i == best and counts[i]:
            work.append(f'<g transform="{place}">{implant(kind)}</g>')
            notes.append(f'<text x="{x:.0f}" y="{y + (apex + 14 if not upper else apex - 2):.0f}" text-anchor="middle" '
                         f'class="mono amber" font-size="9.500">{day(recent[i][0])}</text>')
            continue
        teeth.append(f'<g transform="{place}">{tooth_art(kind)}</g>')
        done = dental_work(kind, level(i))
        if done:
            work.append(f'<g transform="{place}">{done}</g>')
    # today is always the 47
    kind, x, y, place = seats()[27]
    t = TEETH[kind]
    notes.append(f'<g transform="{place}"><path class="pulse" d="{t["top"]}{t["roots"]}" fill="none" '
                 f'stroke="{TEAL}" stroke-width="2.2"/></g>'
                 f'<text x="{x:.0f}" y="{y + t["apex"] + 12:.0f}" text-anchor="middle" class="mono teal" font-size="9.500">today</text>')

    q1, q2, q3 = cuts
    if rest and len(rest) >= 4:
        key = (f"filling = 1–{q1 - 1} contributions · large filling = {q1}–{q2 - 1} · "
               f"filling + root filling = {q2}–{q3 - 1} · crown + root filling = {q3}+")
    else:
        key = "more work that day, more work on the tooth"
    off = sum(1 for c in counts if not c)
    defs = (
        '<filter id="haze" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="26"/></filter>'
        '<filter id="blur1" x="-5%" y="-5%" width="110%" height="110%"><feGaussianBlur stdDeviation="1.1"/></filter>'
        '<filter id="blur2" x="-5%" y="-5%" width="110%" height="110%"><feGaussianBlur stdDeviation="2.2"/></filter>'
        '<filter id="blur3" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="9"/></filter>'
        '<filter id="film"><feGaussianBlur stdDeviation=".55"/></filter>'
        '<filter id="crisp"><feGaussianBlur stdDeviation=".3"/></filter>'
        '<filter id="trabeculae" x="0" y="0" width="100%" height="100%">'
        '<feTurbulence type="fractalNoise" baseFrequency=".2 .26" numOctaves="2" seed="4"/>'
        '<feColorMatrix values="0 0 0 0 .55  0 0 0 0 .62  0 0 0 0 .68  0 0 0 1.5 -.55"/>'
        '<feComposite in2="SourceGraphic" operator="in"/></filter>'
        '<filter id="grain" x="0" y="0" width="100%" height="100%">'
        '<feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="2" seed="11"/>'
        '<feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .55 -.2"/></filter>'
        '<radialGradient id="vig" cx=".5" cy=".5" r=".8"><stop offset=".72" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#000" stop-opacity=".5"/></radialGradient>'
        '<clipPath id="pane"><rect x="16" y="44" width="808" height="372" rx="10"/></clipPath>'
        '<linearGradient id="density" gradientUnits="userSpaceOnUse" x1="0" y1="-130" x2="0" y2="184">'
        '<stop offset="0" stop-color="#232d36"/><stop offset=".5" stop-color="#2d3843"/>'
        '<stop offset="1" stop-color="#3b4854"/></linearGradient>'
    )
    body = (
        f'<rect x=".5" y=".5" width="839" height="497" rx="12" fill="{BG}" stroke="{RULE2}"/>'
        f'<text x="24" y="29" class="mono dim" font-size="10" letter-spacing="1.1">PANORAMIC · LAST 28 DAYS · ONE TOOTH PER DAY</text>'
        f'<text x="816" y="29" text-anchor="end" class="mono dim" font-size="10.500">'
        f'<tspan class="teal">{num(sum(counts))}</tspan> contributions · {day(recent[0][0])} → today</text>'
        f'<rect x="16" y="44" width="808" height="372" rx="10" fill="#040608"/>'
        f'<g clip-path="url(#pane)"><g transform="translate(420 222)">'
        f'{anatomy()}'
        f'<g filter="url(#film)">{wisdom_teeth()}{"".join(teeth)}</g>'
        f'<g filter="url(#crisp)">{"".join(work)}</g>'
        f'{"".join(notes)}'
        '<text x="-392" y="182" class="sans" fill="#cfd6dc" font-size="15" font-weight="700">R</text>'
        '<text x="392" y="182" text-anchor="end" class="sans" fill="#cfd6dc" font-size="15" font-weight="700">L</text>'
        '</g>'
        '<rect x="16" y="44" width="808" height="372" filter="url(#grain)" opacity=".14"/>'
        '<rect x="16" y="44" width="808" height="372" fill="url(#vig)"/></g>'
        f'<rect x="16" y="44" width="808" height="372" rx="10" fill="none" stroke="{RULE}"/>'
        f'<text x="24" y="437" class="mono dim" font-size="10">charted 17 → 27, then 37 → 47 · '
        + (f"sound tooth = day off ({off})" if off else "no sound teeth, so no days off")
        + "</text>"
        f'<text x="24" y="453" class="mono dim" font-size="10">{key}</text>'
        f'<text x="24" y="469" class="mono dim" font-size="10"><tspan class="amber">implant</tspan> = busiest day, '
        f'{day(recent[best][0])} ({num(counts[best])} contributions). the tooth did not survive.</text>'
        f'<text x="24" y="485" class="mono faint" font-size="10">the 8s carry no data. the 48 is lying on the IAN canal '
        f'and CANDID would like a CBCT.</text>'
    )
    label = (
        f"The last 28 days of contributions drawn as a panoramic dental radiograph, one tooth per day: "
        f"{num(sum(counts))} contributions, busiest day {day(recent[best][0])} with {num(counts[best])}. "
        "Busier days show more dental work, from a small filling up to a crown and root filling; "
        "the busiest day is an implant."
    )
    return svg(840, 498, label, body, defs=defs)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "dist"
    os.makedirs(out, exist_ok=True)
    total, days = fetch()
    # The calendar can run a day ahead of UTC-based "today"; keep only days that exist.
    today = dt.datetime.now(dt.timezone.utc).date()
    days = [d for d in days if d[0] <= today]
    for name, text in (
        ("stats.svg", draw_stats(total, days)),
        ("activity.svg", draw_activity(days)),
        ("opg.svg", draw_opg(days)),
    ):
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {out}/{name}")


if __name__ == "__main__":
    main()
