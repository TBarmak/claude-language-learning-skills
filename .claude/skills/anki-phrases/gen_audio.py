#!/usr/bin/env python3
"""Add pronunciation audio to an Anki phrases CSV.

Per expression, try sources in order and stop at the first that works:
  1. Forvo   — real human recording (logic ported from anki-lingo/forvo.py)
  2. Piper   — neural TTS (reuses ai-language-tutor's venv + .onnx voices)
  3. macOS `say` — system voice, last-resort fallback

Every clip is normalized to mp3 via ffmpeg and written to <audio-dir>. The tag
[sound:pronunciation_<lang>_<slug>.mp3] is embedded into the explanation field
(right below the description) so it renders on the back of the card. Drop the
mp3s into Anki's media folder and import the CSV.

Usage:
  python gen_audio.py --csv output/spanish_phrases_XXXX.csv --lang es
  python gen_audio.py --csv <path> --lang es --audio-dir output/<name>

Env overrides (defaults point at the local ai-language-tutor checkout):
  PIPER_PYTHON  path to a python with the `piper` module
  PIPER_VOICES  dir holding <voice>.onnx files
"""
import argparse
import os
import re
import subprocess
import sys
import time
import unicodedata

PIPER_PYTHON = os.environ.get(
    "PIPER_PYTHON",
    "/Users/taylor/Development/ai-language-tutor/venv/bin/python",
)
PIPER_VOICES = os.environ.get(
    "PIPER_VOICES",
    "/Users/taylor/Development/ai-language-tutor/voices",
)

# language code -> { forvo section anchor, piper voice basename, macOS say voice }
# `forvo` doubles as the filename language tag so a name is stable no matter
# which source produced the clip (matches Forvo's pronunciation_<lang>_<word>).
#
# `forvo` is the filename language tag (kept stable per language). `regions` is
# the Forvo accent-section preference order tried when scraping; if none of them
# has a recording, the scraper falls back to ANY region present on the page.
# Forvo splits Spanish into es_es (Spain) and es_latam (Latin America), and
# Portuguese into pt (Portugal) and pt_br (Brazil) — a single anchor misses half.
LANGS = {
    "es":    {"forvo": "es_es",  "regions": ["es_latam", "es_es"], "piper": "es_ES-davefx-medium",   "say": "Monica"},
    "fr":    {"forvo": "fr",     "regions": ["fr"],                "piper": "fr_FR-siwis-medium",    "say": "Thomas"},
    "it":    {"forvo": "it",     "regions": ["it"],                "piper": "it_IT-paola-medium",    "say": "Alice"},
    "de":    {"forvo": "de",     "regions": ["de"],                "piper": "de_DE-thorsten-medium", "say": "Anna"},
    "pt-br": {"forvo": "pt_br",  "regions": ["pt_br", "pt"],       "piper": "pt_BR-faber-medium",    "say": "Luciana"},
    "pt-pt": {"forvo": "pt",     "regions": ["pt", "pt_br"],       "piper": None,                    "say": "Joana"},
    "en":    {"forvo": "en_usa", "regions": ["en_usa", "en"],      "piper": "en_US-lessac-medium",   "say": "Samantha"},
    "ja":    {"forvo": "ja",     "regions": ["ja"],                "piper": None,                    "say": "Kyoko"},
    "zh":    {"forvo": "zh",     "regions": ["zh"],                "piper": None,                    "say": "Tingting"},
}

FORVO_HEADERS = {
    "Referer": "https://www.google.com/",
    "Upgrade-Insecure-Requests": "1",
}

# Seconds to wait before each Forvo page request, to avoid tripping its
# burst rate-limiter (403/429) when processing a long list.
FORVO_DELAY = float(os.environ.get("FORVO_DELAY", "1.2"))


def slug(word):
    """Filesystem/Anki-safe token: strip accents, lowercase, non-alnum -> _."""
    norm = unicodedata.normalize("NFKD", word)
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    norm = norm.lower()
    norm = re.sub(r"[^a-z0-9]+", "_", norm).strip("_")
    return norm or "phrase"


def embed_audio(row, tag):
    """Insert the sound tag below the explanation (2nd field) so it renders on
    the back of the card. Falls back to appending if the row is malformed."""
    fields = row.split("|")
    if len(fields) >= 2:
        fields[1] = f"{fields[1]}<br>{tag}"
        return "|".join(fields)
    return f"{row}<br>{tag}"


def to_mp3(src, dst):
    """Transcode any audio file to mp3. Returns True on success."""
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-codec:a", "libmp3lame", "-qscale:a", "4", dst],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0


# --- source 1: Forvo (human recordings) -----------------------------------

def forvo(word, cfg, dst):
    """Download the top Forvo pronunciation and transcode to mp3."""
    try:
        from bs4 import BeautifulSoup
        from curl_cffi import requests as cffi
        import base64
        import urllib.parse
    except ImportError:
        return False

    url = f"https://forvo.com/word/{'_'.join(word.split())}/"
    parts = list(urllib.parse.urlsplit(url))
    parts[2] = urllib.parse.quote(parts[2])
    url = urllib.parse.urlunsplit(parts)

    try:
        # Forvo rate-limits bursts with 403/429. Retry those with backoff;
        # treat a real 404 as "absent" and stop immediately.
        resp = None
        for attempt in range(4):
            time.sleep(FORVO_DELAY)
            resp = cffi.get(url, headers=FORVO_HEADERS, timeout=20, impersonate="chrome")
            if resp.status_code in (403, 429):
                time.sleep(3 * (attempt + 1))
                continue
            break
        if resp is None or not resp.ok:  # 404 = the word genuinely has no Forvo page
            return False
        soup = BeautifulSoup(resp.content, "html.parser")

        # Map every accent section present on the page: region -> <ul>. The page
        # carries all regions regardless of the URL fragment, so a single anchor
        # misses recordings filed under a sibling accent (e.g. es_latam).
        by_region = {}
        for ul in soup.find_all("ul", class_="pronunciations-list"):
            for cls in ul.get("class", []):
                if cls.startswith("pronunciations-list-"):
                    region = cls[len("pronunciations-list-"):]
                    if region and ul.find("li"):
                        by_region.setdefault(region, ul)

        if not by_region:
            return False  # page exists but no pronunciations

        # Try the language's preferred accents first, then any remaining region.
        order = list(cfg.get("regions", [cfg["forvo"]]))
        order += [r for r in by_region if r not in order]

        for region in order:
            ul = by_region.get(region)
            if ul is None:
                continue
            try:
                li = ul.find_all("li")[0]
                onclick = li.find("div", {"class": "play"})["onclick"]
                b64 = onclick.split(",")[2].replace('"', "")
                path = base64.b64decode(b64.encode("ascii")).decode("ascii")
                audio_url = "https://audio00.forvo.com/ogg/" + path
                ogg = cffi.get(audio_url, headers=FORVO_HEADERS, timeout=20,
                               impersonate="chrome")
                if not ogg.ok or not ogg.content:
                    continue
                tmp = dst + ".ogg"
                with open(tmp, "wb") as fh:
                    fh.write(ogg.content)
                ok = to_mp3(tmp, dst)
                os.remove(tmp)
                if ok:
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False


# --- source 2: Piper (neural TTS) ------------------------------------------

def piper(word, cfg, dst):
    voice = cfg["piper"]
    if not voice:
        return False
    onnx = os.path.join(PIPER_VOICES, voice + ".onnx")
    if not (os.path.exists(PIPER_PYTHON) and os.path.exists(onnx)):
        return False
    tmp = dst + ".wav"
    try:
        subprocess.run(
            [PIPER_PYTHON, "-m", "piper", "-m", onnx, "-f", tmp],
            input=word.encode(), check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        ok = to_mp3(tmp, dst)
        return ok
    except Exception:
        return False
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# --- source 3: macOS say ----------------------------------------------------

def say(word, cfg, dst):
    tmp = dst + ".aiff"
    try:
        subprocess.run(["say", "-v", cfg["say"], "-o", tmp, word], check=True)
        ok = to_mp3(tmp, dst)
        return ok
    except Exception:
        return False
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--lang", required=True, help="language code: " + ", ".join(LANGS))
    ap.add_argument("--audio-dir", help="default: <csv dir>/<csv stem>/")
    ap.add_argument("--no-forvo", action="store_true", help="skip Forvo, go straight to TTS")
    ap.add_argument("--force", action="store_true",
                    help="re-fetch even if an mp3 already exists (upgrades TTS clips to Forvo)")
    args = ap.parse_args()

    cfg = LANGS.get(args.lang)
    if not cfg:
        sys.exit(f"unknown --lang {args.lang!r}; known: {', '.join(LANGS)}")

    if not os.path.exists(args.csv):
        sys.exit(f"csv not found: {args.csv}")

    stem = os.path.splitext(os.path.basename(args.csv))[0]
    audio_dir = args.audio_dir or os.path.join(os.path.dirname(args.csv) or ".", stem)
    os.makedirs(audio_dir, exist_ok=True)

    with open(args.csv, encoding="utf-8") as fh:
        rows = [ln.rstrip("\n") for ln in fh if ln.strip()]

    stats = {"forvo": 0, "piper": 0, "say": 0, "failed": 0, "cached": 0}
    out_rows = []
    for i, row in enumerate(rows, 1):
        # strip audio from a previous run so reruns don't stack tags — handles
        # both the old trailing-column form (|[sound:...] or a bare |) and the
        # current embedded-in-explanation form (<br>[sound:...])
        row = re.sub(r"\|(\[sound:[^\]]*\])?$", "", row)
        row = re.sub(r"<br>\[sound:[^\]]*\]", "", row)
        expr = row.split("|", 1)[0].strip()
        fname = f"pronunciation_{cfg['forvo']}_{slug(expr)}.mp3"
        dst = os.path.join(audio_dir, fname)
        tag = f"[sound:{fname}]"

        if not args.force and os.path.exists(dst) and os.path.getsize(dst) > 0:
            stats["cached"] += 1
            print(f"[{i}/{len(rows)}] {expr}  ✓ cached")
            out_rows.append(embed_audio(row, tag))
            continue

        source = None
        if not args.no_forvo and forvo(expr, cfg, dst):
            source = "forvo"
        elif piper(expr, cfg, dst):
            source = "piper"
        elif say(expr, cfg, dst):
            source = "say"

        if source:
            stats[source] += 1
            print(f"[{i}/{len(rows)}] {expr}  ✓ {source}")
            out_rows.append(embed_audio(row, tag))
        else:
            stats["failed"] += 1
            print(f"[{i}/{len(rows)}] {expr}  ✗ no audio")
            out_rows.append(row)  # no tag; row keeps its 3 columns

    with open(args.csv, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out_rows))

    print("\n── audio summary ──")
    print(f"  Forvo (human):   {stats['forvo']}")
    print(f"  Piper (AI):      {stats['piper']}")
    print(f"  say  (AI):       {stats['say']}")
    print(f"  cached (reused): {stats['cached']}")
    print(f"  failed:          {stats['failed']}")
    print(f"  audio dir:       {audio_dir}")


if __name__ == "__main__":
    main()
