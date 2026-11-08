"""Add 100 synthetic art enthusiasts to the configured development database."""

import random
import secrets
import sys
from datetime import timedelta, timezone
from heapq import nsmallest
from pathlib import Path

from sqlalchemy import inspect


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Artwork, BehaviorLog, Favorite, Like, Rating, User, utcnow  # noqa: E402


USER_COUNT = 100
NAME_PREFIXES = ("松间", "纸上", "暮色", "青岚", "橙光", "雨后", "远山", "窗边", "海盐", "浅溪")
NAME_SUFFIXES = ("拾色", "看画", "慢笔", "一角", "观展记", "收藏册", "小径", "随笔", "调色盘", "旅人")


def add_activity(user, artworks, style_ids, exposure, rng, now):
    preferred = {tag.id for tag in user.preferences}
    activity = rng.triangular(0, 1, 0.2)
    view_count = min(len(artworks), round(5 + 35 * activity))
    # Exponential keys select distinct artworks with both shared popularity and individual taste.
    viewed = nsmallest(
        view_count,
        artworks,
        key=lambda artwork: rng.expovariate(
            exposure[artwork.id] * (4 if preferred & style_ids[artwork.id] else 1)
        ),
    )
    liked = rng.sample(viewed, max(1, round(view_count * rng.uniform(0.2, 0.5))))
    saved = rng.sample(liked, max(1, round(len(liked) * rng.uniform(0.3, 0.75))))
    rated = rng.sample(viewed, max(1, round(view_count * rng.uniform(0.1, 0.3))))
    liked_ids = {artwork.id for artwork in liked}
    saved_ids = {artwork.id for artwork in saved}
    rated_ids = {artwork.id for artwork in rated}

    for artwork in viewed:
        artwork_id = artwork.id
        artwork_created = artwork.created_at
        if artwork_created.tzinfo is None:
            artwork_created = artwork_created.replace(tzinfo=timezone.utc)
        start = min(now, max(user.created_at, artwork_created))
        viewed_at = start + (now - start) * rng.random()
        acted_at = viewed_at + min(now - viewed_at, timedelta(seconds=rng.randint(15, 300)))
        target = {"user_id": user.id, "artwork_id": artwork_id}
        actions = ["view"]
        if artwork_id in liked_ids:
            db.session.add(Like(**target))
            actions.append("like")
        if artwork_id in saved_ids:
            db.session.add(Favorite(**target, created_at=acted_at))
            actions.append("favorite")
        if artwork_id in rated_ids:
            scores = (3, 4, 4, 5, 5) if artwork_id in liked_ids else (1, 2, 3, 3, 4, 4, 5)
            db.session.add(Rating(**target, score=rng.choice(scores)))
            actions.append("rate")
        db.session.add_all(
            BehaviorLog(**target, action=action, created_at=viewed_at if action == "view" else acted_at)
            for action in actions
        )


def seed_demo_users():
    app = create_app()
    with app.app_context(), db.session.begin():
        if not inspect(db.engine).has_table("users"):
            raise SystemExit("Initialize the database before adding demo users.")
        usernames = [f"demo_art_{number:03d}" for number in range(1, USER_COUNT + 1)]
        existing = {name.casefold() for name in db.session.scalars(
            db.select(User.username).where(User.username.in_(usernames))
        )}
        if len(existing) == USER_COUNT:
            return 0

        artworks = db.session.scalars(
            db.select(Artwork).where(Artwork.status == "published").order_by(Artwork.id)
        ).all()
        if not artworks:
            raise SystemExit("Publish or import artworks before adding demo users.")
        styles = {tag.id: tag for artwork in artworks for tag in artwork.tags if tag.category == "style"}
        style_ids = {artwork.id: {tag.id for tag in artwork.tags if tag.id in styles} for artwork in artworks}
        styles = [styles[tag_id] for tag_id in sorted(styles)]
        rng = random.Random(20261108)
        exposure = {artwork.id: 0.3 + rng.lognormvariate(0, 0.65) for artwork in artworks}
        names = [prefix + suffix for prefix in NAME_PREFIXES for suffix in NAME_SUFFIXES]
        rng.shuffle(names)
        now = utcnow()
        users = []
        for username, name in zip(usernames, names):
            if username in existing:
                continue
            user = User(
                username=username,
                display_name=name,
                created_at=now - timedelta(seconds=rng.randint(1, 120 * 86400)),
                preferences=rng.sample(styles, min(len(styles), rng.randint(1, 3))),
            )
            user.set_password(secrets.token_urlsafe(24))
            users.append(user)
        db.session.add_all(users)
        db.session.flush()
        for user in users:
            add_activity(user, artworks, style_ids, exposure, rng, now)
        return len(users)


if __name__ == "__main__":
    created = seed_demo_users()
    print(f"Created {created} demo users; {USER_COUNT - created} usernames already existed.")
