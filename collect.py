#!/usr/bin/env python3
"""P2N2 public engagement collector. Free, self-hosted; no paid service or login.

This relies on undocumented PUBLIC Suno page/API responses. Suno can change
these responses or restrict automated access at any moment. Do not work around
blocks or access controls. Requires only Python 3.10+ (stdlib).
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

PROFILE = "https://suno.com/@p2n2"
API = "https://studio-api.prod.suno.com"
SONG_ID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
UUID_IN_HTML = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
SONG_URL_ID = re.compile(r"suno\.com/song/([0-9a-fA-F-]{36})(?:[/?#]|$)")
DATA_DIR = Path(__file__).resolve().parent / "data"
SEEDS = DATA_DIR / "known_public_songs.json"
MAX_SONGS = 180
PAGES = 12


def first(record, *keys):
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def nonnegative_int(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        return int(value) if value >= 0 else None
    if isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        return int(value.strip())
    return None


def normalize_song(record):
    """Strictly retain songs explicitly identified as public and owned by p2n2."""
    if not isinstance(record, dict):
        return None
    kind = str(first(record, "recordType", "record_type", "type") or "song").lower()
    if kind not in ("song", "clip", "audio", "song_schema"):
        return None
    handle = str(first(record, "creatorHandle", "creator_handle", "handle") or "").lstrip("@").lower()
    if handle != "p2n2":
        return None
    public = first(record, "isPublic", "is_public", "public")
    # Suno's public profile should exclude private songs but a separate clip
    # endpoint can still report them. Never publish an explicitly private clip.
    if public is None and str(record.get("visibility", "")).lower() == "public":
        public = True
    if public is not True or record.get("is_trashed") is True or record.get("is_hidden") is True:
        return None
    raw_url = str(first(record, "url", "songUrl", "song_url") or "")
    sid = str(first(record, "id", "clipId", "clip_id") or "")
    if not SONG_ID.fullmatch(sid):
        m = SONG_URL_ID.search(raw_url)
        sid = m.group(1) if m else ""
    if not SONG_ID.fullmatch(sid):
        return None
    title = str(first(record, "title", "songTitle", "song_title") or "Untitled")[:256]
    image = str(first(record, "imageUrl", "image_url", "cover_image_url") or "")
    return {
        "id": sid.lower(), "title": title,
        "url": "https://suno.com/song/" + sid.lower(),
        "created_at": str(first(record, "createdAt", "created_at") or ""),
        "comments": nonnegative_int(first(record, "commentCount", "comment_count")),
        "likes": nonnegative_int(first(record, "upvoteCount", "upvote_count", "likeCount", "like_count")),
        "plays": nonnegative_int(first(record, "playCount", "play_count")),
        "image": image if image.startswith("https://cdn") else "",
    }


def nested_song_records(data):
    """Find song objects even when Suno changes response envelopes."""
    if isinstance(data, list):
        for item in data:
            yield from nested_song_records(item)
    elif isinstance(data, dict):
        if SONG_ID.fullmatch(str(data.get("id", ""))) and (
            "title" in data or "play_count" in data or "playCount" in data
        ):
            yield data
        else:
            for k, value in data.items():
                if k not in ("metadata", "lyrics", "prompt", "description", "history") and isinstance(value, (dict, list)):
                    yield from nested_song_records(value)


def extract_profile_songs(data):
    """Return candidate clips from a profile response, without treating errors as an empty library."""
    songs = {}
    for item in nested_song_records(data):
        # Some profile envelopes put clip details inside {clip: {...}} with a
        # nested handle, while some records don't carry a handle. The final
        # per-clip read must still prove p2n2 ownership before publication.
        sid = str(item.get("id", "")).lower()
        if SONG_ID.fullmatch(sid):
            songs[sid] = item
    return songs


def request_bytes(url, *, timeout=25):
    req = Request(url, headers={"User-Agent": "P2N2-Public-Metrics/1.0 (personal research)",
                                "Accept": "application/json,text/html;q=0.9,*/*;q=0.5"})
    try:
        with urlopen(req, timeout=timeout) as res:
            return res.read(5_000_000)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url.split('?')[0]}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Connection failure at {url.split('?')[0]}: {exc}") from exc


def request_json(url):
    raw = request_bytes(url)
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("Expected JSON from public Suno endpoint; response changed") from exc


def collect():
    """Read public profile pages and public clip metadata, without authentication.

    Returns records and a coverage note. No proxies, CAPTCHA solving, session
    cookies or throttling circumvention. Network failure exits visibly.
    """
    ids = set()
    clips_by_id = {}
    sources = []
    profile_error = None
    for page in range(1, PAGES + 1):
        url = f"{API}/api/profiles/p2n2?playlists_sort_by=created_at&clips_sort_by=created_at&page={page}"
        try:
            data = request_json(url)
        except RuntimeError as exc:
            profile_error = str(exc)
            break
        found = extract_profile_songs(data)
        new = set(found) - ids
        if not new:
            break
        ids.update(new)
        clips_by_id.update(found)
        sources.append(f"public profile API page {page}")
        if len(ids) >= MAX_SONGS:
            break
        time.sleep(0.8)

    # HTML fallback: song UUIDs embedded in server-rendered public profile.
    if not ids:
        try:
            html = request_bytes(PROFILE).decode("utf-8", "replace")
            candidates = set(UUID_IN_HTML.findall(html))
            ids.update(c.lower() for c in candidates if c != "00000000-0000-0000-0000-000000000000")
            if ids:
                sources.append("public profile HTML")
        except RuntimeError as exc:
            if not profile_error:
                profile_error = str(exc)

    # Known songs aid discovery; they are never treated as a complete catalogue.
    try:
        seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seeds = []
    ids.update(str(i).lower() for i in seeds if SONG_ID.fullmatch(str(i)))
    if not ids:
        raise RuntimeError("No public song identifiers found. Public profile unavailable: " + str(profile_error))
    if not sources:
        sources.append("known public song IDs only (partial catalogue)")

    results = []
    failures = 0
    for sid in sorted(ids)[:MAX_SONGS]:
        # Direct public clip detail is used for confirmed ownership and counts.
        try:
            detail = request_json(f"{API}/api/clip/{sid}")
            if isinstance(detail, dict) and isinstance(detail.get("clip"), dict):
                detail = detail["clip"]
            if isinstance(detail, dict):
                row = normalize_song(detail)
                if row:
                    results.append(detail)
            else:
                failures += 1
        except RuntimeError as exc:
            failures += 1
            if failures <= 3:
                print("Public song read failed: " + str(exc), file=sys.stderr)
        time.sleep(0.75)
    if not results:
        raise RuntimeError("No public P2N2 song metadata could be read. Check connectivity, site changes, or access restrictions.")
    if failures > max(5, len(ids) * 0.2):
        raise RuntimeError(f"{failures} public clip requests failed. Catalogue might be incomplete. Old snapshot retained.")
    print(f"Discovery: {len(ids)} candidate IDs; {len(results)} P2N2 public clips. Source: {', '.join(sources)}")
    return results, ", ".join(sources)


def build_snapshot(items, previous=None, now=None, discovery="test fixture"):
    now = now or datetime.now(timezone.utc)
    songs = {}
    for record in items:
        row = normalize_song(record)
        if not row:
            continue
        existing = songs.get(row["id"])
        if existing is None or sum(row[k] is not None for k in ("comments", "likes", "plays")) > sum(existing[k] is not None for k in ("comments", "likes", "plays")):
            songs[row["id"]] = row
    if not songs:
        raise RuntimeError("No public P2N2 songs found. Old data retained.")
    old_count = len((previous or {}).get("songs", []))
    if old_count >= 10 and len(songs) < old_count * 0.7:
        raise RuntimeError(f"Only {len(songs)} of {old_count} previous songs returned. Suspected incomplete scrape; old data retained.")
    if all(row["comments"] is None for row in songs.values()):
        raise RuntimeError("no comment counts returned. A ranked dashboard cannot be built. Old data retained.")
    rows = sorted(songs.values(), key=lambda s: (s["comments"] is not None, s["comments"] or 0, s["likes"] or 0), reverse=True)
    prev_map = {s["id"]: s for s in (previous or {}).get("songs", [])}
    for s in rows:
        p = prev_map.get(s["id"])
        for k in ("comments", "likes", "plays"):
            s["delta_" + k] = (s[k] - p[k]) if p and s[k] is not None and p.get(k) is not None else None
    return {
        "schema": 1, "source": "Public Suno profile/clip pages (unofficial, no paid service)",
        "discovery": discovery, "profile": PROFILE,
        "catalogue_coverage": "Partial or unverified: Suno public pages are not guaranteed to expose every song",
        "collected_at": now.isoformat(timespec="seconds"),
        "songs_found": len(rows), "songs": rows,
        "metrics_coverage": {k: sum(r[k] is not None for r in rows) for k in ("comments", "likes", "plays")},
    }


def main():
    parser = argparse.ArgumentParser(description="Collect P2N2 public song engagement with no paid service")
    parser.add_argument("--fixture", type=Path, help="Validate local song JSON, no network")
    args = parser.parse_args()
    if args.fixture:
        items = json.loads(args.fixture.read_text(encoding="utf-8"))
        discovery = "offline fixture"
    else:
        items, discovery = collect()
    previous_path = DATA_DIR / "engagement.json"
    try:
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    snapshot = build_snapshot(items, previous=previous, discovery=discovery)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = previous_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(previous_path)
    history_path = DATA_DIR / "history.json"
    try:
        history = json.loads(history_path.read_text(encoding="utf-8"))
        if not isinstance(history, list):
            history = []
    except (OSError, ValueError):
        history = []
    day = snapshot["collected_at"][:10]
    entry = {"date": day, "collected_at": snapshot["collected_at"],
             "songs": [{"id": s["id"], "comments": s["comments"], "likes": s["likes"], "plays": s["plays"]} for s in snapshot["songs"]]}
    history = [h for h in history if h.get("date") != day] + [entry]
    history.sort(key=lambda h: h["date"])
    history_path.write_text(json.dumps(history[-365:], ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Collected {len(snapshot['songs'])} public songs. Coverage: {snapshot['metrics_coverage']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("COLLECTION FAILED: " + str(exc), file=sys.stderr)
        sys.exit(1)
