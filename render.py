#!/usr/bin/env python3
"""kdash2 renderer: builds a 1072x1448 8-bit grayscale PNG for a Kindle Paperwhite 3.
Sources are independent; any that fail are drawn as 'unavailable' instead of crashing.
Usage: python3 render.py [out.png]   (stdlib + Pillow only)"""
import json, math, os, sys, datetime as dt, urllib.request, xml.etree.ElementTree as ET, html, re
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

W, H = 1072, 1448
TZ = ZoneInfo("America/Chicago")
LAT, LON, PLACE = 33.0198, -96.6989, "Plano, TX"
CLOCK_BOX = (560, 14, 1052, 180)
SIZES = [(600, 800), (758, 1024), (1072, 1448), (1236, 1648), (1264, 1680), (1860, 2480)]
DEFAULT_SIZE = (600, 800)   # keep in sync with OVERLAY_* in Kindle config.sh
TEAMS = [("football/nfl", "dal", "Cowboys"), ("basketball/nba", "dal", "Mavericks"),
         ("baseball/mlb", "tex", "Rangers"), ("hockey/nhl", "dal", "Stars")]
TICKERS = [("^GSPC", "S&P 500"), ("AAPL", "AAPL"), ("TSLA", "TSLA"), ("NVDA", "NVDA")]
FEEDS = [("Free Press", "https://www.thefp.com/feed"),
         ("Daily Wire", "https://www.dailywire.com/feeds/rss.xml"),
         ("Fox", "https://moxie.foxnews.com/google-publisher/politics.xml"),
         ("OutKick", "https://www.outkick.com/feed/"),
         ("Sport & State", "https://sportandstate.com/feed"),
         ("Hot Air", "https://hotair.com/feed")]
UA = {"User-Agent": "Mozilla/5.0 (kdash2 e-ink dashboard)"}
HERE = os.path.dirname(os.path.abspath(__file__))
BLACK, DARK, MID, LIGHT, WHITE = 0, 60, 120, 200, 255

def get(url, t=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t) as r:
        return r.read()
def getj(url): return json.loads(get(url))
def safe(fn):
    try: return fn()
    except Exception as e:
        print(f"[warn] {fn.__name__}: {e!r}", file=sys.stderr); return None

def font(sz, bold=False, serif=False):
    n = "DejaVuSerif-Bold.ttf" if serif else ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    return ImageFont.truetype(os.path.join(HERE, "fonts", n), sz)

# ---------------- data sources ----------------
def weather():
    u = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
         "&current=is_day,temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m"
         "&hourly=temperature_2m,precipitation_probability,weather_code,is_day"
         "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
         "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=America%%2FChicago&forecast_days=6") % (LAT, LON)
    return getj(u)

def team(path, abbr, name):
    d = getj(f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{abbr}/schedule")
    last = nxt = None
    for ev in d.get("events", []):
        st = ev["competitions"][0]["status"]["type"]["state"]
        if st == "post": last = ev
        elif nxt is None: nxt = ev
    def fmt_last(ev):
        c = ev["competitions"][0]; me = op = None
        for x in c["competitors"]:
            if x["team"]["abbreviation"].lower() == abbr: me = x
            else: op = x
        s = lambda x: (x.get("score") or {}).get("displayValue", "?")
        wl = "W" if me.get("winner") else ("L" if op.get("winner") else "T")
        at = "vs" if me.get("homeAway") == "home" else "@"
        return f"{wl} {s(me)}-{s(op)} {at} {op['team']['abbreviation']}"
    def fmt_next(ev):
        c = ev["competitions"][0]
        op = [x for x in c["competitors"] if x["team"]["abbreviation"].lower() != abbr][0]
        me = [x for x in c["competitors"] if x["team"]["abbreviation"].lower() == abbr][0]
        at = "vs" if me.get("homeAway") == "home" else "@"
        t = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(TZ)
        live = c["status"]["type"]["state"] == "in"
        if live:
            s = lambda x: (x.get("score") or {}).get("displayValue", "?")
            return f"LIVE {s(me)}-{s(op)} {at} {op['team']['abbreviation']}"
        return f"Next {at} {op['team']['abbreviation']} {t:%a %-m/%-d %-I:%M%p}".replace("AM", "a").replace("PM", "p")
    return name, (fmt_last(last) if last else "—"), (fmt_next(nxt) if nxt else "Season over")

def quote(sym):
    d = getj("https://query1.finance.yahoo.com/v8/finance/chart/%s?range=5d&interval=1d" % urllib.request.quote(sym))
    m = d["chart"]["result"][0]["meta"]
    p = m["regularMarketPrice"]; prev = m.get("chartPreviousClose") or m.get("previousClose")
    pct = m.get("regularMarketChangePercent")
    if pct is None and prev: pct = (p - prev) / prev * 100
    return p, pct

def headlines():
    out = []
    for src, url in FEEDS:
        try:
            root = ET.fromstring(get(url, 15))
            items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            for n, it in enumerate(items[:3]):
                t = it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title") or ""
                t = re.sub(r"\s+", " ", html.unescape(t)).strip()
                if t: out.append((n, src, t))
        except Exception as e:
            print(f"[warn] feed {src}: {e!r}", file=sys.stderr)
    out.sort(key=lambda x: x[0])  # one per source first
    return [(s, t) for _, s, t in out]

def moon(now):
    days = (now.astimezone(dt.timezone.utc) - dt.datetime(2000, 1, 6, 18, 14, tzinfo=dt.timezone.utc)).total_seconds() / 86400
    age = days % 29.530588853; f = age / 29.530588853
    names = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous", "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]
    return f, names[int((f * 8) + 0.5) % 8], (1 - math.cos(2 * math.pi * f)) / 2

WMO = {0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
       51: "Drizzle", 53: "Drizzle", 55: "Drizzle", 56: "Frz Drizzle", 57: "Frz Drizzle", 61: "Light Rain", 63: "Rain",
       65: "Heavy Rain", 66: "Frz Rain", 67: "Frz Rain", 71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 77: "Snow",
       80: "Showers", 81: "Showers", 82: "Heavy Showers", 85: "Snow Showers", 86: "Snow Showers",
       95: "T-Storms", 96: "T-Storms", 99: "T-Storms"}

# ---------------- drawing helpers ----------------
def icon(d, code, cx, cy, r, night=False):
    """Simple vector weather glyphs (crisp on e-ink)."""
    if night and code in (0, 1):
        d.ellipse((cx-r*0.5, cy-r*0.5, cx+r*0.5, cy+r*0.5), fill=BLACK)
        d.ellipse((cx-r*0.25, cy-r*0.65, cx+r*0.7, cy+r*0.3), fill=WHITE)
        return
    def sun(x, y, rr):
        d.ellipse((x-rr, y-rr, x+rr, y+rr), fill=BLACK)
        for k in range(8):
            a = k * math.pi / 4
            d.line((x+rr*1.35*math.cos(a), y+rr*1.35*math.sin(a), x+rr*1.8*math.cos(a), y+rr*1.8*math.sin(a)), fill=BLACK, width=max(2, int(rr/5)))
    def cloud(x, y, rr, fill=MID):
        for dx, dy, s in ((-0.55, 0.1, 0.55), (0.0, -0.25, 0.7), (0.6, 0.1, 0.5)):
            d.ellipse((x+dx*rr-s*rr, y+dy*rr-s*rr, x+dx*rr+s*rr, y+dy*rr+s*rr), fill=fill, outline=BLACK, width=3)
        d.rectangle((x-1.05*rr, y+0.1*rr, x+1.05*rr, y+0.6*rr), fill=fill)
        d.line((x-1.05*rr, y+0.6*rr, x+1.05*rr, y+0.6*rr), fill=BLACK, width=3)
    if code in (0,): sun(cx, cy, r*0.5)
    elif code in (1, 2): sun(cx-r*0.3, cy-r*0.3, r*0.38); cloud(cx+r*0.15, cy+r*0.15, r*0.6, WHITE)
    elif code in (3, 45, 48): cloud(cx, cy, r*0.75)
    else:
        cloud(cx, cy-r*0.2, r*0.7)
        if code >= 95:
            d.polygon([(cx, cy+r*0.4), (cx-r*0.2, cy+r*0.8), (cx, cy+r*0.75), (cx-r*0.1, cy+r*1.1), (cx+r*0.2, cy+r*0.6), (cx, cy+r*0.65)], fill=BLACK)
        else:
            snow = code in (71, 73, 75, 77, 85, 86)
            for k in (-1, 0, 1):
                x = cx + k*r*0.4
                if snow: d.ellipse((x-6, cy+r*0.6-6, x+6, cy+r*0.6+6), fill=BLACK)
                else: d.line((x, cy+r*0.45, x-r*0.12, cy+r*0.85), fill=BLACK, width=4)

def tw(d, s, f): return d.textlength(s, font=f)
def ctext(d, x, y, s, f, fill=BLACK): d.text((x - tw(d, s, f)/2, y), s, font=f, fill=fill)
def rtext(d, x, y, s, f, fill=BLACK): d.text((x - tw(d, s, f), y), s, font=f, fill=fill)
def fit(d, s, f, maxw):
    if tw(d, s, f) <= maxw: return s
    while s and tw(d, s + "…", f) > maxw: s = s[:-1]
    return s.rstrip() + "…"
def wrap(d, s, f, maxw, lines=2):
    words, out, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if tw(d, t, f) <= maxw: cur = t
        else:
            out.append(cur); cur = w
            if len(out) == lines: break
    if len(out) < lines and cur: out.append(cur)
    if len(out) == lines and " ".join(out) != s: out[-1] = fit(d, out[-1] + " …", f, maxw)
    return out
def section(d, y, title):
    f = font(26, True)
    d.text((40, y), title.upper(), font=f, fill=BLACK)
    x0 = 40 + tw(d, title.upper(), f) + 16
    d.line((x0, y + 16, W - 40, y + 16), fill=BLACK, width=3)
    return y + 44

def r(x): return "--" if x is None else str(int(math.floor(x + 0.5)))

# ---------------- render ----------------
def render(out):
    now = dt.datetime.now(TZ)
    wx = safe(weather)
    sports = [safe(lambda t=t: team(*t)) for t in TEAMS]
    quotes = [(lab, safe(lambda s=s: quote(s))) for s, lab in TICKERS]
    news = safe(headlines) or []

    im = Image.new("L", (W, H), WHITE); d = ImageDraw.Draw(im)

    # Header: date left, clock box right (Kindle may overlay a live clock here)
    d.text((40, 22), now.strftime("%A"), font=font(52, True), fill=BLACK)
    d.text((40, 86), now.strftime("%B %-d, %Y"), font=font(36), fill=DARK)
    d.text((40, 136), PLACE, font=font(26), fill=MID)
    cb = CLOCK_BOX
    rtext(d, cb[2], cb[1] - 12, now.strftime("%-I:%M"), font(140, True))
    d.line((40, 190, W - 40, 190), fill=BLACK, width=5)

    y = 204
    if wx:
        c, dl, hr = wx["current"], wx["daily"], wx["hourly"]
        icon(d, c["weather_code"], 130, y + 100, 88, night=not c["is_day"])
        d.text((250, y - 5), r(c["temperature_2m"]) + "°", font=font(160, True), fill=BLACK)
        x2 = 640
        d.text((x2, y + 10), WMO.get(c["weather_code"], "—"), font=font(44, True), fill=BLACK)
        d.text((x2, y + 68), f"High {r(dl['temperature_2m_max'][0])}°  Low {r(dl['temperature_2m_min'][0])}°", font=font(32), fill=BLACK)
        d.text((x2, y + 110), f"Feels {r(c['apparent_temperature'])}°  Rain {r(dl['precipitation_probability_max'][0])}%", font=font(28), fill=DARK)
        d.text((x2, y + 148), f"Wind {r(c['wind_speed_10m'])} mph  Hum {r(c['relative_humidity_2m'])}%", font=font(28), fill=DARK)
        sr = dt.datetime.fromisoformat(dl["sunrise"][0]); ss = dt.datetime.fromisoformat(dl["sunset"][0])
        f_, mname, illum = moon(now)
        d.text((x2, y + 186), f"↑ {sr:%-I:%M}  ↓ {ss:%-I:%M}  ☾ {mname}", font=font(26), fill=DARK)
        y += 214

        # Hourly: next 8 slots every 2 hours with rain bars
        y = section(d, y, "Next 16 hours")
        times = [dt.datetime.fromisoformat(t).replace(tzinfo=TZ) for t in hr["time"]]
        i0 = next((i for i, t in enumerate(times) if t >= now.replace(minute=0, second=0, microsecond=0)), 0)
        idx = [i0 + 2*k for k in range(8) if i0 + 2*k < len(times)]
        cw = (W - 80) / 8
        for k, i in enumerate(idx):
            cx = 40 + cw*k + cw/2
            ctext(d, cx, y, times[i].strftime("%-I%p").lower(), font(24, True), BLACK)
            icon(d, hr["weather_code"][i], cx, y + 58, 28, night=not hr["is_day"][i])
            ctext(d, cx, y + 92, r(hr["temperature_2m"][i]) + "°", font(32, True))
            p = hr["precipitation_probability"][i] or 0
            bx0, bx1, by1 = cx - 34, cx + 34, y + 166
            d.rectangle((bx0, by1 - 36, bx1, by1), outline=BLACK, width=2)
            if p: d.rectangle((bx0, by1 - 36*p/100, bx1, by1), fill=DARK)
            ctext(d, cx, by1 + 4, f"{p}%", font(22), BLACK)
        y += 196

        # Daily
        y = section(d, y, "Forecast")
        cw = (W - 80) / 5
        for k in range(1, 6):
            if k >= len(dl["time"]): break
            cx = 40 + cw*(k-1) + cw/2
            day = dt.date.fromisoformat(dl["time"][k])
            ctext(d, cx, y, day.strftime("%a"), font(28, True))
            icon(d, dl["weather_code"][k], cx, y + 64, 30)
            ctext(d, cx, y + 102, f"{r(dl['temperature_2m_max'][k])}° / {r(dl['temperature_2m_min'][k])}°", font(28, True))
            ctext(d, cx, y + 136, f"rain {r(dl['precipitation_probability_max'][k])}%", font(22), DARK)
        y += 172
    else:
        d.text((40, y + 60), "Weather unavailable", font=font(44, True)); y += 640

    # Sports 2x2
    y = section(d, y, "Dallas sports")
    colw = (W - 80) / 2
    for k, s in enumerate(sports):
        x = 40 + colw*(k % 2); yy = y + 72*(k // 2)
        name = TEAMS[k][2]
        d.text((x, yy), name, font=font(28, True), fill=BLACK)
        if s:
            d.text((x + 190, yy), fit(d, s[1], font(28), colw - 200), font=font(28), fill=BLACK)
            d.text((x, yy + 36), fit(d, s[2], font(24), colw - 20), font=font(24), fill=DARK)
        else:
            d.text((x + 190, yy), "unavailable", font=font(26), fill=MID)
    y += 150

    # Markets
    y = section(d, y, "Markets")
    cw = (W - 80) / 4
    for k, (lab, q) in enumerate(quotes):
        x = 40 + cw*k
        d.text((x, y), lab, font=font(26, True), fill=BLACK)
        if q:
            p, pct = q
            d.text((x, y + 32), f"{p:,.2f}", font=font(30, True), fill=BLACK)
            if pct is not None:
                s = f"{'▲' if pct >= 0 else '▼'} {abs(pct):.2f}%"
                d.text((x, y + 70), s, font=font(26, pct < 0), fill=BLACK)
        else:
            d.text((x, y + 32), "n/a", font=font(28), fill=MID)
    y += 100

    # Headlines
    y = section(d, y, "Headlines")
    fH, fS = font(24), font(17, True)
    bottom = H - 50
    LH = 34
    nfit = max(1, (bottom - y) // LH)
    if news:
        # rotate through all headlines: each 15-min render shows the next window
        slot = (now.hour * 60 + now.minute) // 15
        k0 = (slot * nfit) % len(news)
        news = (news[k0:] + news[:k0])[:nfit]
    for src, t in news:
        lines = wrap(d, t, fH, W - 40 - 205, 1)
        need = LH
        if y + need > bottom: break
        d.text((40, y + 5), src.upper(), font=fS, fill=DARK)
        for j, ln in enumerate(lines): d.text((205, y + 32*j), ln, font=fH, fill=BLACK)
        y += need
    if not news: d.text((40, y), "Headlines unavailable", font=font(26), fill=MID)

    # Footer
    d.line((40, H - 44, W - 40, H - 44), fill=BLACK, width=2)
    d.text((40, H - 36), f"Updated {now:%-I:%M %p %a}", font=font(22), fill=DARK)
    rtext(d, W - 40, H - 36, "Open-Meteo · ESPN · Yahoo · RSS", font(22), DARK)

    base, ext = os.path.splitext(out)
    def fitted(w, h):
        if (w, h) == im.size: return im
        k = min(w / W, h / H)
        sc = im.resize((round(W * k), round(H * k)), Image.LANCZOS)
        c = Image.new("L", (w, h), WHITE); c.paste(sc, ((w - sc.width) // 2, (h - sc.height) // 2))
        return c
    # Common Kindle framebuffer sizes; the Kindle picks dash-<W>x<H>.png from `fbink -e`.
    for w, h in SIZES:
        fitted(w, h).save(f"{base}-{w}x{h}{ext}", optimize=True)
    dw, dh = DEFAULT_SIZE
    fitted(dw, dh).save(out, optimize=True)     # dash.png fallback = size seen in user's photo
    print("wrote", out, "and size variants")

if __name__ == "__main__":
    render(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "sample.png"))
