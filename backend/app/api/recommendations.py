from collections import Counter, defaultdict

from flask import abort, jsonify, request

from ..extensions import db
from ..models import Artwork, BehaviorLog, Favorite, Like, Rating, RecommendationSetting
from . import api
from .common import current_user


def _setting(key, default):
    row = db.session.get(RecommendationSetting, key)
    try:
        return max(0.0, float(row.value)) if row else default
    except ValueError:
        return default


def _popular_counts():
    weights = {"view": 1, "like": 3, "favorite": 4, "rate": 2}
    counts = Counter()
    for artwork_id, action, count in db.session.execute(
        db.select(BehaviorLog.artwork_id, BehaviorLog.action, db.func.count())
        .group_by(BehaviorLog.artwork_id, BehaviorLog.action)
    ):
        counts[artwork_id] += weights.get(action, 0) * count
    return counts


def _personal_scores(user, artworks, popularity):
    scores = defaultdict(float)
    tag_weight = _setting("tag_weight", 3.0)
    cf_weight = _setting("itemcf_weight", 2.0)
    favorite_ids = set(db.session.scalars(db.select(Favorite.artwork_id).where(Favorite.user_id == user.id)))
    liked_ids = set(db.session.scalars(db.select(Like.artwork_id).where(Like.user_id == user.id)))
    rated = dict(db.session.execute(db.select(Rating.artwork_id, Rating.score).where(Rating.user_id == user.id)).all())
    source_ids = favorite_ids | liked_ids | {artwork_id for artwork_id, score in rated.items() if score >= 4}
    by_id = {item.id: item for item in artworks}
    preference_ids = {tag.id for tag in user.preferences}
    # ItemCF: users who liked/favorited the same works vote for their other works.
    peers = set(db.session.scalars(db.select(Favorite.user_id).where(Favorite.artwork_id.in_(source_ids)))) if source_ids else set()
    peers |= set(db.session.scalars(db.select(Like.user_id).where(Like.artwork_id.in_(source_ids)))) if source_ids else set()
    peers.discard(user.id)
    peer_votes = Counter()
    if peers:
        peer_votes.update(db.session.scalars(db.select(Favorite.artwork_id).where(Favorite.user_id.in_(peers))))
        peer_votes.update(db.session.scalars(db.select(Like.artwork_id).where(Like.user_id.in_(peers))))
    for artwork in artworks:
        tag_ids = {tag.id for tag in artwork.tags}
        scores[artwork.id] = (
            tag_weight * len(tag_ids & preference_ids)
            + cf_weight * peer_votes[artwork.id]
            + 0.2 * popularity[artwork.id]
            + (5 if artwork.featured else 0)
        )
        for source_id in source_ids:
            source = by_id.get(source_id)
            if source and source.id != artwork.id:
                overlap = len(tag_ids & {tag.id for tag in source.tags})
                scores[artwork.id] += cf_weight * overlap * (rated.get(source_id, 4) / 5)
    return scores, source_ids


@api.get("/recommendations")
def recommendations():
    kind = request.args.get("kind", "personal")
    if kind not in ("personal", "hot", "latest"):
        abort(400, description="kind 必须是 personal、hot 或 latest")
    artworks = db.session.scalars(db.select(Artwork).where(Artwork.status == "published")).all()
    popularity = _popular_counts()
    user = current_user()
    if kind == "latest":
        ranked = sorted(artworks, key=lambda a: (a.created_at, a.id), reverse=True)
    elif kind == "hot" or not user:
        ranked = sorted(artworks, key=lambda a: (a.featured, popularity[a.id], a.created_at, a.id), reverse=True)
    else:
        scores, source_ids = _personal_scores(user, artworks, popularity)
        ranked = sorted(artworks, key=lambda a: (a.id not in source_ids, scores[a.id], a.created_at, a.id), reverse=True)
    return jsonify(kind=kind, items=[item.to_dict() for item in ranked[:20]])
