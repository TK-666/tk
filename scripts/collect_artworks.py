"""Extend the attributed public-domain artwork catalog from AIC.

Run with backend/.venv/Scripts/python.exe scripts/collect_artworks.py from the
repository root. Requests are serial and separated by at least one second.
"""

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data"
API = "https://api.artic.edu/api/v1/artworks/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 art-recommendation-graduation-project",
    "AIC-User-Agent": "art-recommendation-graduation-project",
}
IMAGE_WIDTH = 843
STYLES = (
    ("Impressionism", "印象派", 120),
    ("Post-Impressionism", "后印象派", 35),
    ("Realism", "写实主义", 28),
    ("Renaissance", "文艺复兴", 20),
    ("Baroque", "巴洛克", 5),
    ("Pointillism", "点彩派", 1),
    ("Chinese (culture or style)", "国风", 115),
    ("Neoclassicism", "新古典主义", 5),
    ("Japanese (culture or style)", "日本绘画", 65),
    ("South Asian", "南亚绘画", 52),
    ("Himalayan", "喜马拉雅绘画", 30),
    ("Folk Art", "民间艺术", 12),
    ("Modernism", "现代主义", 12),
)
FIELDS = ",".join((
    "id", "title", "image_id", "artist_title", "artist_display",
    "date_display", "date_start", "style_title", "subject_titles",
    "medium_display", "credit_line", "is_public_domain", "artwork_type_title",
))
TOPICS = {
    "风景": {"landscape", "landscapes", "landscape painting", "nature"},
    "城市": {"cityscapes", "urban life", "street"},
    "肖像": {"portrait", "portraits", "portraiture", "portraits: female subject", "portraits: male subject", "self-portraits"},
    "静物": {"still life", "still lifes"},
    "人物": {"figures", "figure", "everyday life (genre)", "people", "women", "men", "woman", "man", "children"},
    "花卉": {"flowers", "floral", "flower"},
    "海景": {"seascapes", "seascape"},
    "动物": {"animals", "birds", "horses", "dogs", "cats", "fish", "insects"},
    "山水": {"mountains", "mountain", "rivers", "river", "lakes", "lake", "waterfalls"},
    "建筑": {"architecture", "building", "buildings", "house", "houses", "castles", "bridges"},
    "室内": {"interior", "interiors", "bedrooms", "domestic scenes"},
    "宗教": {"religion", "religious", "religious scenes", "religious figures", "devotion", "christian subjects", "christianity", "biblical", "buddhism", "hinduism", "jain", "saints"},
    "音乐": {"music", "musicians", "musical instruments"},
    "家庭": {"family", "families", "mother", "woman with children", "domestic life"},
    "乡村生活": {"rural life", "farmers", "farming", "peasants", "agriculture"},
    "休闲": {"leisure", "recreation", "sports", "games"},
    "劳动": {"work", "labor", "workers"},
    "服饰": {"fashion", "clothing", "costume", "costumes"},
    "航船": {"boats", "ships", "sailing", "sailboats"},
    "夜景": {"night scenes", "nocturnes", "moonlight"},
    "季节与天气": {"weather/seasons", "rain", "snow", "storms", "winter", "summer", "autumn", "spring"},
}

# Apply narrower phrases to the artwork title before any series or source citation.
TITLE_TOPICS = {
    "风景": r"landscapes?",
    "肖像": r"portraits?",
    "静物": r"still lifes?",
    "花卉": r"flowers?|lotus|orchids?|chrysanthemums?|(?:plum|peach) blossoms?",
    "海景": r"seascapes?",
    "动物": r"birds?|horses?|dogs?|cats?|fish|insects?|elephants?|ducks?|geese|deer",
    "山水": r"mountains?|rivers?|lakes?|waterfalls?",
    "建筑": r"temples?|pagodas?|bridges?|pavilions?",
    "宗教": r"buddhas?|bodhisattvas?|buddhist|mandalas?|christ|madonna|krishna|shiva|arhats?",
    "音乐": r"music|musicians?|lutes?|flutes?",
    "航船": r"boats?|ships?|sailboats?",
    "夜景": r"at night|by moonlight|nocturne",
}

MEDIUMS = (
    (r"oil", "油画"),
    (r"watercolou?r", "水彩"),
    (r"tempera", "蛋彩"),
    (r"pastels?", "粉彩"),
    (r"ink", "水墨"),
    (r"gouache", "水粉"),
    (r"charcoal", "炭笔"),
    (r"graphite", "石墨"),
    (r"paper", "纸本"),
    (r"silk", "绢本"),
    (r"canvas", "布面"),
    (r"wood|wooden panel|on panel", "木板"),
    (r"cotton", "棉布"),
    (r"gold", "金彩"),
)


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
            except (URLError, TimeoutError) as error:
                permanent = isinstance(error, HTTPError) and 400 <= error.code < 500 and error.code != 429
                if permanent or attempt == 2:
                    raise RuntimeError(f"AIC request failed: {request.full_url}: {error}") from error
                time.sleep(2 ** attempt)


def tags_for(record, style_name):
    tags = [{"category": "style", "name": style_name}]
    subjects = {value.strip().casefold() for value in record.get("subject_titles") or []}
    title = re.split(r",\s+(?:from|page from)\b", record["title"].casefold(), maxsplit=1)[0]
    for topic, names in TOPICS.items():
        title_terms = TITLE_TOPICS.get(topic)
        if subjects & names or (title_terms and re.search(rf"\b(?:{title_terms})\b", title)):
            tags.append({"category": "topic", "name": topic})
    medium = (record.get("medium_display") or "").casefold()
    for pattern, name in MEDIUMS:
        if re.search(rf"\b(?:{pattern})\b", medium):
            tags.append({"category": "medium", "name": name})
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
        "limit": 100,
        "fields": FIELDS,
    }
    for page in range(1, 11):
        body["page"] = page
        params = urlencode({"params": json.dumps(body, separators=(",", ":"))})
        request = Request(f"{API}?{params}", headers=HEADERS)
        result = json.loads(client.fetch(request))
        yield from result["data"]
        if page >= result["pagination"]["total_pages"]:
            break


def write_manifest(path, manifest):
    pending = path.with_suffix(".json.tmp")
    pending.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def refresh_catalog_tags(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    style_names = {original: localized for original, localized, _ in STYLES}
    changed = 0
    for item in manifest["artworks"]:
        inferred = tags_for(item, style_names[item["style_title"]])
        missing = [tag for tag in inferred if tag not in item["tags"]]
        if missing:
            item["tags"].extend(missing)
            changed += 1
    if changed:
        write_manifest(path, manifest)
    print(f"Added tags to {changed}/{len(manifest['artworks'])} catalog artworks")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-tags", action="store_true", help="append tags from saved museum metadata without downloading images")
    args = parser.parse_args()
    manifest_path = OUTPUT / "artworks.json"
    if args.refresh_tags:
        refresh_catalog_tags(manifest_path)
        return

    image_dir = OUTPUT / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    artworks = json.loads(manifest_path.read_text(encoding="utf-8"))["artworks"] if manifest_path.exists() else []
    for item in artworks:
        path = OUTPUT / item["image_file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["image_sha256"]:
            raise ValueError(f"Existing catalog image has changed: {path}")
    source_ids = {item["source_id"] for item in artworks}
    image_ids = {item["iiif_url"].split("/")[5] for item in artworks}
    image_hashes = {item["image_sha256"] for item in artworks}
    counts = Counter(item["style_title"] for item in artworks)
    client = MuseumClient()
    for english_style, chinese_style, target in STYLES:
        selected = counts[english_style]
        if selected >= target:
            continue
        for record in search(client, english_style):
            identifier = record.get("image_id")
            if not (record.get("is_public_domain") is True
                    and record.get("style_title") == english_style
                    and record.get("artwork_type_title") == "Painting"
                    and isinstance(record.get("id"), int)
                    and isinstance(record.get("title"), str)
                    and 0 < len(record["title"]) <= 160
                    and isinstance(identifier, str)
                    and re.fullmatch(r"[0-9a-f-]{36}", identifier)):
                continue
            artwork_id = record["id"]
            if artwork_id in source_ids or identifier in image_ids:
                continue
            filename = f"aic-{artwork_id}.jpg"
            path = image_dir / filename
            image_url = f"https://www.artic.edu/iiif/2/{identifier}/full/{IMAGE_WIDTH},/0/default.jpg"
            try:
                raw = path.read_bytes() if path.exists() else client.fetch(Request(image_url, headers=HEADERS))
                with Image.open(BytesIO(raw)) as image:
                    if image.format != "JPEG" or image.width > IMAGE_WIDTH:
                        raise ValueError("Unexpected image format or dimensions")
                    image.load()
            except (RuntimeError, ValueError, OSError) as error:
                print(f"Skipping image {artwork_id}: {error}")
                continue
            image_hash = hashlib.sha256(raw).hexdigest()
            if image_hash in image_hashes:
                continue
            if not path.exists():
                path.write_bytes(raw)
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
                "image_sha256": image_hash,
            })
            source_ids.add(artwork_id)
            image_ids.add(identifier)
            image_hashes.add(image_hash)
            selected += 1
            print(f"{english_style}: {selected}/{target} — {record['title']}")
            if selected == target:
                break
        if selected < target:
            raise RuntimeError(f"Only collected {selected}/{target} for {english_style}")
    if manifest_path.exists() and len(artworks) == sum(counts.values()):
        print(f"Catalog already contains {len(artworks)} artworks and meets all style targets")
        return
    manifest = {
        "source": "Art Institute of Chicago public API",
        "source_docs": "https://api.artic.edu/docs/",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "artworks": artworks,
    }
    write_manifest(manifest_path, manifest)
    print(f"Saved {len(artworks)} artworks to {OUTPUT}")


if __name__ == "__main__":
    main()
