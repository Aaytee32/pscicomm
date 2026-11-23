"""Upload finished videos to Cloudinary, log their links, and rebuild the PSciComm site (site/).

Usage:
    python upload.py films/deafness.mp4
    python upload.py films/            (every .mp4, .mov, .m4v or .webm in the folder)
    python upload.py films/ --force    (re-upload even if unchanged)

Videos already in the log are skipped unless the file has changed since it was uploaded,
so re-exporting a fixed version uploads it again automatically.

Credentials come from CLOUDINARY_URL in your .env file. Never hard-code them here.
"""
import argparse
import csv
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # must run before importing cloudinary, so it sees CLOUDINARY_URL

import cloudinary  # noqa: E402
import cloudinary.uploader  # noqa: E402

import build_page  # noqa: E402

cloudinary.config(secure=True)  # always return https links

ASSET_FOLDER = "science-shorts"   # folder name inside your Cloudinary Media Library
LOG_FILE = build_page.LOG_FILE    # uploads_log.csv, always next to this script
LOG_FIELDS = ["uploaded_at", "file", "public_id", "seconds", "width", "height", "url"]
VIDEO_TYPES = {".mp4", ".mov", ".m4v", ".webm"}
FREE_PLAN_LIMIT_MB = 100          # Free plan max video size; raise it if you upgrade


def upload(video: Path) -> dict:
    size_mb = video.stat().st_size / 1_000_000
    if size_mb > FREE_PLAN_LIMIT_MB:
        raise ValueError(f"{video.name} is {size_mb:.0f} MB, over the {FREE_PLAN_LIMIT_MB} MB plan limit")
    return cloudinary.uploader.upload_large(
        str(video),
        resource_type="video",
        asset_folder=ASSET_FOLDER,
        public_id=video.stem,       # the file name becomes the video's ID
        overwrite=True,             # re-uploading a fixed version replaces the old one
        chunk_size=6_000_000,       # send in 6 MB pieces, so big files survive a shaky connection
    )


def read_log() -> list[dict]:
    if not LOG_FILE.exists():
        return []
    with LOG_FILE.open(newline="") as f:
        return list(csv.DictReader(f))


def last_uploaded(rows: list[dict]) -> dict[str, datetime]:
    """public_id -> when it was last uploaded."""
    return {r["public_id"]: datetime.fromisoformat(r["uploaded_at"]) for r in rows}


def log(video: Path, result: dict) -> None:
    rows = read_log()
    if rows and list(rows[0].keys()) != LOG_FIELDS:
        # log was written by an older version of this script: rewrite it with the new columns
        with LOG_FILE.open("w", newline="") as f:
            w = csv.DictWriter(f, LOG_FIELDS, restval="", extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="") as f:
        w = csv.DictWriter(f, LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({
            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
            "file": video.name,
            "public_id": result.get("public_id"),
            "seconds": result.get("duration"),
            "width": result.get("width"),
            "height": result.get("height"),
            "url": result.get("secure_url"),
        })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", type=Path, help="a video file, or a folder of videos")
    parser.add_argument("--force", action="store_true", help="re-upload even if unchanged since last upload")
    args = parser.parse_args()

    target = args.target
    if target.is_dir():
        videos = sorted(p for p in target.iterdir() if p.suffix.lower() in VIDEO_TYPES)
    else:
        videos = [target]
    if not videos:
        parser.exit(1, f"No video files ({', '.join(sorted(VIDEO_TYPES))}) found at {target}\n")

    done = last_uploaded(read_log())
    uploaded = skipped = failed = 0
    for v in videos:
        prev = done.get(v.stem)
        if prev and not args.force and v.exists() and datetime.fromtimestamp(v.stat().st_mtime) <= prev:
            print(f"SKIP    {v.name} (unchanged since {prev:%Y-%m-%d %H:%M}; --force to re-upload)")
            skipped += 1
            continue
        try:
            result = upload(v)
        except Exception as e:  # keep going if one file fails
            print(f"FAILED  {v.name}: {e}")
            failed += 1
            continue
        log(v, result)
        print(f"OK      {v.name} -> {result['secure_url']}")
        uploaded += 1

    print(f"\n{uploaded} uploaded, {skipped} skipped, {failed} failed")
    if uploaded:
        print(f"Site rebuilt: {build_page.build()}")


if __name__ == "__main__":
    main()
