"""Create or enrich 100 synthetic art enthusiasts in the development database."""

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


def as_utc(timestamp):
    # SQLite returns naive timestamps even for UTC columns.
    return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp


def add_activity(user, artworks, tag_ids, topics, exposure, now):
    rng = random.Random(f"20261108:{user.username}")
    view_target = min(len(artworks), round(23 + 140 * rng.betavariate(2, 3)))
    actions = (
        ("like", Like, rng.uniform(0.17, 0.52), "unlike"),
        ("favorite", Favorite, rng.uniform(0.10, 0.35), "unfavorite"),
        ("rate", Rating, rng.uniform(0.08, 0.30), None),
    )
    rating_bias = rng.uniform(-0.6, 0.6)
    preferred_styles = {tag.id for tag in user.preferences}
    topic = rng.choice(topics) if topics else None
    taste = {
        artwork_id: rng.uniform(0.6, 1.6) + 1.4 * bool(preferred_styles & tags) + 0.9 * (topic in tags)
        for artwork_id, tags in tag_ids.items()
    }

    views = {}
    reversed_actions = {"unlike": set(), "unfavorite": set()}
    history = db.session.execute(db.select(BehaviorLog.artwork_id, BehaviorLog.action, BehaviorLog.created_at).where(
        BehaviorLog.user_id == user.id, BehaviorLog.action.in_(("view", "unlike", "unfavorite"))
    ))
    for artwork_id, action, created_at in history:
        if artwork_id not in tag_ids:
            continue
        if action == "view":
            timestamp = as_utc(created_at)
            views[artwork_id] = min(views.get(artwork_id, timestamp), timestamp)
        else:
            reversed_actions[action].add(artwork_id)

    new_views = nsmallest(
        max(0, view_target - len(views)),
        (artwork for artwork in artworks if artwork.id not in views),
        key=lambda artwork: rng.expovariate(exposure[artwork.id] * taste[artwork.id]),
    )
    for artwork in new_views:
        start = min(now, max(as_utc(user.created_at), as_utc(artwork.created_at), now - timedelta(days=30)))
        viewed_at = start + (now - start) * rng.random()
        views[artwork.id] = viewed_at
        db.session.add(BehaviorLog(user_id=user.id, artwork_id=artwork.id, action="view", created_at=viewed_at))

    added = len(new_views)
    liked = set()
    for action, model, rate, reversal in actions:
        active = set(db.session.scalars(db.select(model.artwork_id).where(model.user_id == user.id))) & tag_ids.keys()
        candidates = views.keys() - active - reversed_actions.get(reversal, set())
        selected = nsmallest(
            max(0, max(1, round(view_target * rate)) - len(active)),
            sorted(candidates),
            key=lambda artwork_id: rng.expovariate(taste[artwork_id] * (1.4 if artwork_id in liked else 1)),
        )
        if action == "like":
            liked = active.union(selected)
        added += len(selected)
        for artwork_id in selected:
            viewed_at = min(now, views[artwork_id])
            acted_at = viewed_at + min(now - viewed_at, timedelta(seconds=rng.randint(15, 300)))
            values = {"user_id": user.id, "artwork_id": artwork_id}
            if action == "favorite":
                values["created_at"] = acted_at
            elif action == "rate":
                mean = 2.8 + rating_bias + 0.4 * (taste[artwork_id] - 1) + 0.5 * (artwork_id in liked)
                values["score"] = max(1, min(5, round(rng.gauss(mean, 0.95))))
            db.session.add(model(**values))
            db.session.add(BehaviorLog(user_id=user.id, artwork_id=artwork_id, action=action, created_at=acted_at))
    return added > 0


def seed_demo_users():
    app = create_app()
    with app.app_context(), db.session.begin():
        if not inspect(db.engine).has_table("users"):
            raise SystemExit("Initialize the database before adding demo users.")
        usernames = [f"demo_art_{number:03d}" for number in range(1, USER_COUNT + 1)]
        existing = {user.username.casefold(): user for user in db.session.scalars(
            db.select(User).where(User.username.in_(usernames))
        )}

        artworks = db.session.scalars(
            db.select(Artwork).where(Artwork.status == "published").order_by(Artwork.id)
        ).all()
        if not artworks:
            raise SystemExit("Publish or import artworks before adding demo users.")
        styles = {tag.id: tag for artwork in artworks for tag in artwork.tags if tag.category == "style"}
        tag_ids = {artwork.id: {tag.id for tag in artwork.tags} for artwork in artworks}
        topics = sorted({tag.id for artwork in artworks for tag in artwork.tags if tag.category == "topic"})
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
        updated = 0
        for user in users + list(existing.values()):
            if user.role == "user" and add_activity(user, artworks, tag_ids, topics, exposure, now):
                updated += 1
        return len(users), updated


if __name__ == "__main__":
    created, updated = seed_demo_users()
    print(f"Created {created} demo users; added interactions for {updated} demo users.")
