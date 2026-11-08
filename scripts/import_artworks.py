"""Import the checked-in AIC sample catalog into the configured database.

Run with backend/.venv/Scripts/python.exe scripts/import_artworks.py from the
repository root after `flask --app run init-db`. Existing artworks are kept.
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy import inspect, or_


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Artwork, Tag  # noqa: E402


MANIFEST = ROOT / "data" / "artworks.json"
CATEGORIES = {"style", "topic", "medium", "era"}


def load_catalog():
    catalog = json.loads(MANIFEST.read_text(encoding="utf-8"))
    artworks = catalog.get("artworks")
    if catalog.get("source") != "Art Institute of Chicago public API" or not isinstance(artworks, list) or not artworks:
        raise ValueError("Invalid or empty artwork catalog")
    seen = set()
    for item in artworks:
        source_id = item.get("source_id")
        if not isinstance(source_id, int) or source_id in seen or item.get("is_public_domain") is not True:
            raise ValueError(f"Invalid or duplicate public-domain source ID: {source_id}")
        seen.add(source_id)
        filename = f"aic-{source_id}.jpg"
        if item.get("image_file") != f"images/{filename}":
            raise ValueError(f"Unexpected image path for {source_id}")
        path = ROOT / "data" / "images" / filename
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item.get("image_sha256"):
            raise ValueError(f"Missing or changed image: {path}")
        with Image.open(path) as image:
            if image.format != "JPEG":
                raise ValueError(f"Image is not JPEG: {path}")
            image.verify()
        if not isinstance(item.get("title"), str) or not 0 < len(item["title"]) <= 160:
            raise ValueError(f"Invalid title for {source_id}")
        if not isinstance(item.get("tags"), list) or not any(tag.get("category") == "style" for tag in item["tags"]):
            raise ValueError(f"Missing style tag for {source_id}")
        for tag in item["tags"]:
            if tag.get("category") not in CATEGORIES or not isinstance(tag.get("name"), str) or not 0 < len(tag["name"]) <= 60:
                raise ValueError(f"Invalid tag for {source_id}")
        if item.get("source_url") != f"https://www.artic.edu/artworks/{source_id}":
            raise ValueError(f"Invalid source URL for {source_id}")
    return artworks


def ensure_images(item, upload_dir):
    source_id = item["source_id"]
    original = f"aic-{source_id}.jpg"
    cover = f"aic-{source_id}-cover.webp"
    source = ROOT / "data" / "images" / original
    target = upload_dir / original
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != item["image_sha256"]:
            raise ValueError(f"Existing upload differs from collected image: {target}")
    else:
        shutil.copy2(source, target)
    cover_path = upload_dir / cover
    if not cover_path.exists():
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((600, 600))
            image.save(cover_path, "WEBP", quality=82)
    return f"/api/uploads/{original}", f"/api/uploads/{cover}"


def import_catalog(artworks, *, update_tags=False):
    app = create_app()
    with app.app_context():
        if not inspect(db.engine).has_table("artworks"):
            raise RuntimeError("Database tables are missing; run flask --app run init-db first")
        upload_dir = Path(app.config["UPLOAD_FOLDER"])
        upload_dir.mkdir(parents=True, exist_ok=True)
        tags_by_key = {(tag.category, tag.name): tag for tag in db.session.scalars(db.select(Tag))}
        created = updated = skipped = 0
        for item in artworks:
            image_url, cover_url = ensure_images(item, upload_dir)
            # Some museum IDs are prefixes of other IDs, such as 869 and 86998.
            source_url_pattern = re.escape(item["source_url"]) + r"([^0-9]|$)"
            existing_id = db.session.scalar(db.select(Artwork.id).where(or_(
                Artwork.image_url == image_url,
                Artwork.description.regexp_match(source_url_pattern),
            )).order_by(Artwork.image_url != image_url, Artwork.id))
            if existing_id is not None and not update_tags:
                skipped += 1
                continue
            selected_tags = []
            for entry in item["tags"]:
                key = (entry["category"], entry["name"])
                tag = tags_by_key.get(key)
                if tag is None:
                    tag = Tag(category=key[0], name=key[1])
                    db.session.add(tag)
                    tags_by_key[key] = tag
                selected_tags.append(tag)
            if existing_id is not None:
                artwork = db.session.get(Artwork, existing_id)
                missing = [tag for tag in selected_tags if tag not in artwork.tags]
                if missing:
                    artwork.tags.extend(missing)
                    updated += 1
                else:
                    skipped += 1
                continue

            facts = [f"创作年代：{item['date_display']}" if item.get("date_display") else ""]
            if item.get("medium_display"):
                facts.append(f"材料：{item['medium_display']}")
            facts.append(f"馆藏：芝加哥艺术学院。作品资料：{item['source_url']}")
            if item.get("credit_line"):
                facts.append(f"馆方署名：{item['credit_line']}")
            artwork = Artwork(
                title=item["title"],
                artist=(item.get("artist") or "")[:120],
                artist_bio=item.get("artist_display") or "",
                description="。".join(fact for fact in facts if fact),
                image_url=image_url,
                cover_url=cover_url,
                status="published",
                tags=selected_tags,
            )
            db.session.add(artwork)
            created += 1
        db.session.commit()
        print(f"Database: {db.engine.dialect.name}; created: {created}; tags updated: {updated}; skipped: {skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-tags", action="store_true", help="add missing catalog tags to existing artworks")
    args = parser.parse_args()
    import_catalog(load_catalog(), update_tags=args.update_tags)
