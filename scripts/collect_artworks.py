"""Collect a small, attributed public-domain artwork catalog from AIC.

Run with backend/.venv/Scripts/python.exe scripts/collect_artworks.py from the
repository root. Requests are serial and separated by at least one second.
"""

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data"
API = "https://api.artic.edu/api/v1/artworks/search"
STYLES = (
    ("Impressionism", "印象派", 8),
    ("Post-Impressionism", "后印象派", 8),
    ("Realism", "写实主义", 8),
    ("Renaissance", "文艺复兴", 8),
    ("Baroque", "巴洛克", 5),
    ("Pointillism", "点彩派", 1),
    ("Chinese (culture or style)", "国风", 8),
)
FIELDS = ",".join((
    "id", "title", "image_id", "artist_title", "artist_display",
    "date_display", "date_start", "style_title", "subject_titles",
    "medium_display", "credit_line", "is_public_domain", "artwork_type_title",
))
TOPICS = {
    "风景": {"landscape", "landscapes", "landscape painting", "nature"},
    "城市": {"cityscapes", "urban life", "street"},
    "肖像": {"portrait", "portraits", "portraiture"},
    "静物": {"still life", "still lifes"},
    "人物": {"figures", "figure", "everyday life (genre)"},
    "花卉": {"flowers", "floral"},
    "海景": {"seascapes", "seascape"},
}


class MuseumClient:
    def __init__(self):
        self.last_request = 0.0

    def fetch(self, request):
        for attempt in range(3):
            elapsed = time.monotonic() - self.last_request
            if elapsed < 1.1:
                time.sleep(1.1 - elapsed)
            self.last_request = time.monotonic()
            try:
                with urlopen(request, timeout=30) as response:
                    return response.read()
            except (HTTPError, URLError, TimeoutError) as error:
                if attempt == 2:
                    raise RuntimeError(f"AIC request failed: {request.full_url}") from error
                time.sleep(2 ** attempt)


def tags_for(record, style_name):
    tags = [{"category": "style", "name": style_name}]
    subjects = {str(value).casefold() for value in record.get("subject_titles") or []}
    for topic, names in TOPICS.items():
        if subjects & names:
            tags.append({"category": "topic", "name": topic})
    medium = (record.get("medium_display") or "").casefold()
    for token, name in (("watercolor", "水彩"), ("oil", "油画"), ("tempera", "蛋彩"), ("pastel", "粉彩"), ("ink", "水墨")):
        if token in medium:
            tags.append({"category": "medium", "name": name})
            break
    year = record.get("date_start")
    if isinstance(year, int) and 1000 <= year <= 2100:
        tags.append({"category": "era", "name": f"{(year - 1) // 100 + 1}世纪"})
    return tags


def search(client, style):
    body = {
        "query": {"bool": {"filter": [
            {"term": {"is_public_domain": True}},
            {"term": {"style_title.keyword": style}},
            {"term": {"artwork_type_title.keyword": "Painting"}},
            {"exists": {"field": "image_id"}},
        ]}},
        "limit": 30,
        "fields": FIELDS,
    }
    request = Request(
        API, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 art-recommendation-graduation-project", "AIC-User-Agent": "art-recommendation-graduation-project"},
        method="POST",
    )
    return json.loads(client.fetch(request))["data"]


def main():
    image_dir = OUTPUT / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    client = MuseumClient()
    artworks = []
    for english_style, chinese_style, target in STYLES:
        selected = 0
        for record in search(client, english_style):
            identifier = record.get("image_id")
            if not (record.get("is_public_domain") is True
                    and record.get("style_title") == english_style
                    and record.get("artwork_type_title") == "Painting"
                    and isinstance(record.get("id"), int)
                    and isinstance(record.get("title"), str)
                    and len(record["title"]) <= 160
                    and isinstance(identifier, str)
                    and re.fullmatch(r"[0-9a-f-]{36}", identifier)):
                continue
            artwork_id = record["id"]
            filename = f"aic-{artwork_id}.jpg"
            path = image_dir / filename
            image_url = f"https://www.artic.edu/iiif/2/{identifier}/full/1200,/0/default.jpg"
            if not path.exists():
                request = Request(image_url, headers={"User-Agent": "Mozilla/5.0 art-recommendation-graduation-project", "AIC-User-Agent": "art-recommendation-graduation-project"})
                try:
                    raw = client.fetch(request)
                    with Image.open(BytesIO(raw)) as image:
                        if image.format != "JPEG" or image.width > 1200:
                            raise ValueError("Unexpected image format or dimensions")
                        image.verify()
                    path.write_bytes(raw)
                except (RuntimeError, ValueError, OSError) as error:
                    print(f"Skipping image {artwork_id}: {error}")
                    continue
            raw = path.read_bytes()
            artworks.append({
                "source": "Art Institute of Chicago",
                "source_id": artwork_id,
                "source_url": f"https://www.artic.edu/artworks/{artwork_id}",
                "api_url": f"https://api.artic.edu/api/v1/artworks/{artwork_id}",
                "iiif_url": image_url,
                "is_public_domain": True,
                "title": record["title"],
                "artist": record.get("artist_title") or "",
                "artist_display": record.get("artist_display") or "",
                "date_display": record.get("date_display") or "",
                "date_start": record.get("date_start"),
                "medium_display": record.get("medium_display") or "",
                "credit_line": record.get("credit_line") or "",
                "style_title": english_style,
                "subject_titles": record.get("subject_titles") or [],
                "tags": tags_for(record, chinese_style),
                "image_file": f"images/{filename}",
                "image_sha256": hashlib.sha256(raw).hexdigest(),
            })
            selected += 1
            print(f"{english_style}: {selected}/{target} — {record['title']}")
            if selected == target:
                break
        if selected < target:
            raise RuntimeError(f"Only collected {selected}/{target} for {english_style}")
    manifest = {
        "source": "Art Institute of Chicago public API",
        "source_docs": "https://api.artic.edu/docs/",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "artworks": artworks,
    }
    (OUTPUT / "artworks.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(artworks)} artworks to {OUTPUT}")


if __name__ == "__main__":
    main()
