"""Build the PSciComm site (site/index.html) from uploads_log.csv and videos.json.

Usage:
    python build_page.py

upload.py runs this automatically after a successful upload, so you rarely need it by hand.

Titles and descriptions live in videos.json, keyed by video ID (the file name without .mp4):
    {
      "isch-flat": {
        "title": "When blood flow to the brain falls",
        "description": "How arterioles dilate to protect the brain as perfusion pressure drops."
      }
    }
Only "title" is needed. Optional fields, shown on the card when present:
    "subtitle"     short line under the title
    "description"  a sentence or two, always visible
    "points"       list of bullets, in a collapsible "In this video" section
    "audience"     one line under the bullets (who it's for)
    "credits"      list of small-print lines: sources, music licences, disclaimers
Every uploaded video is added to videos.json automatically, so you only fill in the text.
"""
import csv
import html
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG_FILE = HERE / "uploads_log.csv"
META_FILE = HERE / "videos.json"
SITE_DIR = HERE / "site"
PAGE_FILE = SITE_DIR / "index.html"

SITE_NAME = "PSciComm"
DOMAIN = "pscicomm.deoyin.com"
TAGLINE = "Short animated explainers that turn pharmacology, physiology and neuroscience into clear visual stories."


def latest_uploads() -> list[dict]:
    """One row per video (the newest upload wins), newest first.

    Each row gets an "episode" number: 1 for the first video ever uploaded, and so on.
    Re-uploading a fixed version keeps the video's original number.
    """
    if not LOG_FILE.exists():
        return []
    with LOG_FILE.open(newline="") as f:
        rows = list(csv.DictReader(f))
    latest, episode = {}, {}
    for row in rows:  # the log is in time order, so later rows overwrite earlier ones
        episode.setdefault(row["public_id"], len(episode) + 1)
        latest[row["public_id"]] = {**row, "episode": episode[row["public_id"]]}
    return sorted(latest.values(), key=lambda r: r["uploaded_at"], reverse=True)


def default_title(public_id: str) -> str:
    return public_id.replace("-", " ").replace("_", " ").title()


def load_meta(rows: list[dict]) -> dict[str, dict]:
    """Read videos.json, adding a stub for any uploaded video that isn't in it yet."""
    meta = json.loads(META_FILE.read_text(encoding="utf-8")) if META_FILE.exists() else {}
    added = [r["public_id"] for r in rows if r["public_id"] not in meta]
    for pid in added:
        meta[pid] = {"title": default_title(pid), "description": ""}
    if added or not META_FILE.exists():
        META_FILE.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for pid in added:
            print(f"Added {pid} to {META_FILE.name}: give it a title and description there")
    return meta


def cloudinary_variant(url: str, transformation: str, ext: str | None = None) -> str:
    """Insert a Cloudinary transformation into a delivery URL (e.g. q_auto for smaller files)."""
    out = url.replace("/video/upload/", f"/video/upload/{transformation}/", 1)
    if ext:
        out = out.rsplit(".", 1)[0] + "." + ext
    return out


def poster_url(url: str) -> str:
    return cloudinary_variant(url, "so_10p,w_720", "jpg")  # a frame 10% of the way in


def duration(seconds: str) -> str:
    try:
        s = round(float(seconds))
    except (TypeError, ValueError):
        return ""
    return f"{s // 60}:{s % 60:02d}"


def card(row: dict, info: dict) -> str:
    index = row["episode"]
    e = html.escape
    url = row["url"]
    title = info.get("title") or default_title(row["public_id"])
    desc = info.get("description", "").strip()
    w, h = row.get("width") or "9", row.get("height") or "16"  # unknown size: assume a vertical short
    length = duration(row["seconds"])
    subtitle = info.get("subtitle", "").strip()
    points = [p for p in info.get("points", []) if p.strip()]
    audience = info.get("audience", "").strip()
    credits = [c for c in info.get("credits", []) if c.strip()]

    extra = ""
    if subtitle:
        extra += f'\n        <p class="video-subtitle">{e(subtitle)}</p>'
    if desc:
        extra += f'\n        <p class="video-desc">{e(desc)}</p>'
    if points or audience:
        items = "".join(f"<li>{e(p)}</li>" for p in points)
        details = f"<ul>{items}</ul>" if items else ""
        if audience:
            details += f'<p class="video-audience">{e(audience)}</p>'
        extra += f'\n        <details class="video-more"><summary>In this video</summary>{details}</details>'
    if credits:
        extra += '\n        <div class="video-credits">' + "".join(f"<p>{e(c)}</p>" for c in credits) + "</div>"

    try:
        wide = float(w) > float(h)  # landscape videos get a double-width card
    except ValueError:
        wide = False
    classes = "video-card wide" if wide else "video-card"

    return f"""    <article class="{classes}" id="{e(row["public_id"])}">
      <video controls preload="none" playsinline poster="{e(poster_url(url))}" style="aspect-ratio: {e(w)} / {e(h)}" aria-label="{e(title)}">
        <source src="{e(cloudinary_variant(url, "q_auto"))}" type="video/mp4">
      </video>
      <div class="video-body">
        <div class="video-meta"><span>{index:02d}</span><span>{length}</span></div>
        <h2 class="video-title">{e(title)}</h2>{extra}
      </div>
    </article>"""


def build() -> Path:
    rows = latest_uploads()
    meta = load_meta(rows)
    cards = "\n".join(card(r, meta.get(r["public_id"], {})) for r in rows)
    if not cards:
        cards = '    <p class="empty">New videos coming soon.</p>'
    count = f'{len(rows)} video{"" if len(rows) == 1 else "s"}'
    og_image = poster_url(rows[0]["url"]) if rows else f"https://{DOMAIN}/favicon.svg"
    e = html.escape

    SITE_DIR.mkdir(exist_ok=True)
    (SITE_DIR / "CNAME").write_text(DOMAIN + "\n")  # tells GitHub Pages which domain to serve
    (SITE_DIR / "favicon.svg").write_text(FAVICON, encoding="utf-8")
    PAGE_FILE.write_text(PAGE.format(
        name=SITE_NAME, domain=DOMAIN, tagline=e(TAGLINE), count=count,
        og_image=e(og_image), cards=cards,
    ), encoding="utf-8")
    return PAGE_FILE


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" fill="#090c10"/>
  <text x="32" y="42" font-family="'Space Mono', monospace" font-size="28" font-weight="700" fill="#c9a84c" text-anchor="middle">PS</text>
</svg>
"""

# Styled to match deoyin.com: same palette, fonts and grid background.
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} | Science explainers by Deoyin & Company</title>
<meta name="description" content="{tagline}">
<link rel="canonical" href="https://{domain}/">
<meta property="og:type" content="website">
<meta property="og:title" content="{name} | Science explainers by Deoyin & Company">
<meta property="og:description" content="{tagline}">
<meta property="og:url" content="https://{domain}/">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<link rel="preconnect" href="https://res.cloudinary.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Urbanist:wght@300;400;600;700;800&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #090c10; --bg2: #0e1218; --bg3: #141920; --border: rgba(255,255,255,0.07);
    --gold: #c9a84c; --gold-glow: rgba(201,168,76,0.08);
    --text: #e8eaf0; --text-muted: #6b7280; --text-mid: #9ca3af;
    --mono: 'Space Mono', monospace; --display: 'Urbanist', system-ui, sans-serif;
    color-scheme: dark;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{
      --bg: #f7f5f0; --bg2: #ffffff; --bg3: #f0ede4; --border: rgba(9,12,16,0.09);
      --gold: #a8842f; --gold-glow: rgba(168,132,47,0.08);
      --text: #14171c; --text-muted: #8b8578; --text-mid: #52504a;
      color-scheme: light;
    }}
  }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--display); min-height: 100vh; }}
  body::before {{
    content: ''; position: fixed; inset: 0; pointer-events: none; z-index: 0;
    background-image: linear-gradient(var(--gold-glow) 1px, transparent 1px), linear-gradient(90deg, var(--gold-glow) 1px, transparent 1px);
    background-size: 48px 48px;
  }}
  .wrap {{ position: relative; z-index: 1; max-width: 1080px; margin: 0 auto; padding: 0 2rem; }}
  nav {{ border-bottom: 1px solid var(--border); padding: 1.1rem 0; }}
  nav .wrap {{ display: flex; justify-content: space-between; align-items: center; gap: 1rem; }}
  .logo, .nav-link {{ font-family: var(--mono); text-transform: uppercase; text-decoration: none; }}
  .logo {{ font-size: 13px; letter-spacing: 0.12em; color: var(--gold); }}
  .nav-link {{ font-size: 11px; letter-spacing: 0.08em; color: var(--text-muted); }}
  .nav-link:hover {{ color: var(--gold); }}
  header {{ padding: 4.5rem 0 3rem; }}
  .eyebrow {{ font-family: var(--mono); font-size: 11px; letter-spacing: 0.2em; color: var(--gold); text-transform: uppercase;
              margin-bottom: 1rem; display: flex; align-items: center; gap: 10px; }}
  .eyebrow::before {{ content: ''; width: 32px; height: 1px; background: var(--gold); }}
  h1 {{ font-size: clamp(2.6rem, 7vw, 4.2rem); font-weight: 800; line-height: 1; letter-spacing: -0.03em; margin-bottom: 1.25rem; }}
  .sub {{ font-size: 1.05rem; color: var(--text-mid); max-width: 560px; line-height: 1.75; font-weight: 300; }}
  .label {{ font-family: var(--mono); font-size: 10px; letter-spacing: 0.25em; text-transform: uppercase; color: var(--text-muted);
            margin-bottom: 1.5rem; display: flex; align-items: center; gap: 12px; }}
  .label::after {{ content: ''; flex: 1; height: 1px; background: var(--border); }}
  .videos {{ display: grid; gap: 1.5rem; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); align-items: start;
              grid-auto-flow: dense; padding-bottom: 5rem; }}  /* dense: a portrait card fills the gap a wide card leaves */
  .video-card {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }}
  @media (min-width: 640px) {{ .video-card.wide {{ grid-column: span 2; }} }}
  .video-card video {{ display: block; width: 100%; height: auto; background: #000; }}
  .video-body {{ padding: 1.1rem 1.25rem 1.35rem; }}
  .video-meta {{ display: flex; justify-content: space-between; font-family: var(--mono); font-size: 10px; letter-spacing: 0.1em;
                 color: var(--text-muted); margin-bottom: 0.6rem; font-variant-numeric: tabular-nums; }}
  .video-title {{ font-size: 1.15rem; font-weight: 700; line-height: 1.25; letter-spacing: -0.01em; }}
  .video-subtitle {{ margin-top: 0.3rem; font-family: var(--mono); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--gold); }}
  .video-desc {{ margin-top: 0.6rem; font-size: 0.85rem; line-height: 1.6; color: var(--text-mid); font-weight: 300; }}
  .video-more {{ margin-top: 0.9rem; border-top: 1px solid var(--border); padding-top: 0.75rem; font-size: 0.8rem; line-height: 1.55; color: var(--text-mid); font-weight: 300; }}
  .video-more summary {{ cursor: pointer; font-family: var(--mono); font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-muted); list-style: none; }}
  .video-more summary::-webkit-details-marker {{ display: none; }}
  .video-more summary::before {{ content: '+ '; color: var(--gold); }}
  .video-more[open] summary::before {{ content: '\\2212  '; }}
  .video-more summary:hover {{ color: var(--gold); }}
  .video-more ul {{ margin: 0.6rem 0 0 1rem; display: grid; gap: 0.35rem; }}
  .video-audience {{ margin-top: 0.6rem; font-style: italic; }}
  .video-credits {{ margin-top: 0.9rem; font-size: 0.7rem; line-height: 1.5; color: var(--text-muted); display: grid; gap: 0.25rem; }}
  .empty {{ color: var(--text-muted); }}
  footer {{ border-top: 1px solid var(--border); padding: 1.5rem 0; font-family: var(--mono); font-size: 10px;
            letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-muted); }}
  footer .wrap {{ display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }}
  footer a {{ color: inherit; text-decoration: none; }}
  footer a:hover {{ color: var(--gold); }}
  @media (max-width: 600px) {{ .wrap {{ padding: 0 1.25rem; }} header {{ padding: 3rem 0 2rem; }} }}
</style>
</head>
<body>
<nav><div class="wrap">
  <a class="logo" href="./">{name}</a>
  <a class="nav-link" href="https://deoyin.com/">Deoyin &amp; Company &#8599;</a>
</div></nav>
<header><div class="wrap">
  <div class="eyebrow">Science communication</div>
  <h1>{name}</h1>
  <p class="sub">{tagline}</p>
</div></header>
<main class="wrap">
  <div class="label">{count}</div>
  <section class="videos">
{cards}
  </section>
</main>
<footer><div class="wrap">
  <span>&copy; Deoyin &amp; Company LLC</span>
  <a href="https://deoyin.com/">deoyin.com</a>
</div></footer>
</body>
</html>
"""


if __name__ == "__main__":
    print(f"Wrote {build()}")
