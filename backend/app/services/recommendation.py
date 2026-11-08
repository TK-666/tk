"""Small-catalog hybrid recommendations using tags and item-based CF.

Scores are calculated on demand. For a larger catalog, cache or precompute the
item similarity matrix rather than running this service for every request.
"""

from collections import Counter, defaultdict
from itertools import combinations
from math import log1p, log2, sqrt

from ..extensions import db
from ..models import Artwork, BehaviorLog, Favorite, Like, Rating, RecommendationSetting, User


def _weight(key, default):
    row = db.session.get(RecommendationSetting, key)
    if not row:
        return default
    try:
        value = float(row.value)
    except (TypeError, ValueError):
        return default
    return value if 0 <= value <= 100 else default


def _signals():
    """Return positive user-item strengths, popularity, and disliked items.

    Current likes/favorites/ratings are authoritative; action logs for those
    controls can include removals and retries, so only view logs are counted.
    Repeated views are capped to keep refreshes from dominating rankings.
    """
    enabled_users = set(db.session.scalars(db.select(User.id).where(User.enabled.is_(True))))
    views = {}
    for user_id, artwork_id, count in db.session.execute(
        db.select(BehaviorLog.user_id, BehaviorLog.artwork_id, db.func.count())
        .join(Artwork, Artwork.id == BehaviorLog.artwork_id)
        .where(Artwork.status == "published", BehaviorLog.action == "view")
        .group_by(BehaviorLog.user_id, BehaviorLog.artwork_id)
    ):
        if user_id in enabled_users:
            views[user_id, artwork_id] = min(count, 3)

    likes = {(user_id, artwork_id) for user_id, artwork_id in db.session.execute(
        db.select(Like.user_id, Like.artwork_id)
        .join(Artwork, Artwork.id == Like.artwork_id)
        .where(Artwork.status == "published")
    )}
    favorites = {(user_id, artwork_id) for user_id, artwork_id in db.session.execute(
        db.select(Favorite.user_id, Favorite.artwork_id)
        .join(Artwork, Artwork.id == Favorite.artwork_id)
        .where(Artwork.status == "published")
    )}
    ratings = {(user_id, artwork_id): score for user_id, artwork_id, score in db.session.execute(
        db.select(Rating.user_id, Rating.artwork_id, Rating.score)
        .join(Artwork, Artwork.id == Rating.artwork_id)
        .where(Artwork.status == "published")
    ) if user_id in enabled_users}

    profiles = defaultdict(dict)
    popularity = Counter()
    disliked = defaultdict(set)
    for user_id, artwork_id in views.keys() | likes | favorites | ratings.keys():
        if user_id not in enabled_users:
            continue
        score = ratings.get((user_id, artwork_id))
        if score is not None and score <= 2:
            disliked[user_id].add(artwork_id)
            continue
        view_count = views.get((user_id, artwork_id), 0)
        liked = (user_id, artwork_id) in likes
        favorited = (user_id, artwork_id) in favorites
        positive_rating = max(0, (score or 0) - 3)
        strength = 0.2 * view_count + 2.0 * liked + 3.0 * favorited + positive_rating
        if strength:
            profiles[user_id][artwork_id] = strength
        popularity[artwork_id] += 0.25 * view_count + 2.0 * liked + 3.0 * favorited + positive_rating
    return profiles, popularity, disliked


def _item_similarities(profiles):
    """Return adjusted cosine similarity and shared user count for each item pair."""
    norms = Counter()
    cooccurrence = Counter()
    shared_users = Counter()
    for profile in profiles.values():
        capped = {artwork_id: min(strength, 5.0) for artwork_id, strength in profile.items()}
        for artwork_id, strength in capped.items():
            norms[artwork_id] += strength * strength
        if len(capped) < 2:
            continue
        activity_penalty = log2(len(capped) + 1)
        for (left_id, left_strength), (right_id, right_strength) in combinations(sorted(capped.items()), 2):
            pair = (left_id, right_id)
            cooccurrence[pair] += left_strength * right_strength / activity_penalty
            shared_users[pair] += 1
    return {
        pair: (shared / sqrt(norms[pair[0]] * norms[pair[1]]), shared_users[pair])
        for pair, shared in cooccurrence.items()
    }


def _tag_affinity(user, profile, by_id):
    affinity = defaultdict(float)
    explicit_styles = {tag.id for tag in user.preferences if tag.category == "style"}
    for tag_id in explicit_styles:
        affinity[tag_id] = 1.0
    for artwork_id, strength in profile.items():
        artwork = by_id.get(artwork_id)
        if not artwork:
            continue
        for tag in artwork.tags:
            factor = 0.6 if tag.category == "style" else 0.2
            affinity[tag.id] += factor * min(strength, 3.0) / 3.0
    return affinity, explicit_styles


def _serialize(artwork, reason, itemcf_evidence=None):
    result = artwork.to_dict()
    result["recommendation_reason"] = reason
    if itemcf_evidence is not None:
        result["itemcf_evidence"] = itemcf_evidence
    return result


def recommend(kind, user, limit=20):
    artworks = db.session.scalars(db.select(Artwork).where(Artwork.status == "published")).all()
    if not artworks:
        return {"kind": kind, "strategy": "empty", "items": []}
    if kind == "latest":
        ranked = sorted(artworks, key=lambda item: (item.created_at, item.id), reverse=True)
        return {"kind": kind, "strategy": "latest", "items": [_serialize(item, "最新上传") for item in ranked[:limit]]}

    profiles, popularity, disliked = _signals()
    hot = sorted(
        artworks,
        key=lambda item: (item.featured, popularity[item.id], item.created_at, item.id),
        reverse=True,
    )
    if kind == "hot" or user is None:
        strategy = "hot" if kind == "hot" else "guest_fallback"
        return {"kind": kind, "strategy": strategy, "items": [
            _serialize(item, "编辑精选" if item.featured else "热门作品") for item in hot[:limit]
        ]}

    profile = profiles.get(user.id, {})
    by_id = {item.id: item for item in artworks}
    affinity, explicit_styles = _tag_affinity(user, profile, by_id)
    if not profile and not explicit_styles:
        visible = [item for item in hot if item.id not in disliked.get(user.id, set())]
        return {"kind": kind, "strategy": "cold_start", "items": [
            _serialize(item, "编辑精选" if item.featured else "热门作品") for item in visible[:limit]
        ]}

    tag_weight = _weight("tag_weight", 3.0)
    cf_weight = _weight("itemcf_weight", 2.0)
    similarities = _item_similarities(profiles) if profile and cf_weight else {}
    scored = []
    for artwork in artworks:
        if artwork.id in disliked.get(user.id, set()):
            continue
        tag_score = tag_weight * sum(affinity[tag.id] for tag in artwork.tags)
        cf_total = 0.0
        evidence = None
        if similarities:
            best_contribution = 0.0
            source_with_evidence = None
            peer_count_with_evidence = 0
            own_overlap = int(artwork.id in profile)
            for source_id, strength in profile.items():
                pair = tuple(sorted((source_id, artwork.id)))
                pair_stats = similarities.get(pair)
                if pair_stats is None:
                    continue
                similarity, shared_users = pair_stats
                contribution = strength * similarity
                cf_total += contribution
                peer_count = shared_users - own_overlap
                if peer_count > 0 and contribution > best_contribution and source_id in by_id:
                    best_contribution = contribution
                    source_with_evidence = source_id
                    peer_count_with_evidence = peer_count
            if source_with_evidence is not None:
                evidence = {
                    "source_artwork_id": source_with_evidence,
                    "source_title": by_id[source_with_evidence].title,
                    "shared_user_count": peer_count_with_evidence,
                }
        cf_score = cf_weight * cf_total
        score = tag_score + cf_score + 0.2 * log1p(popularity[artwork.id]) + (2.0 if artwork.featured else 0.0)
        if evidence and cf_score > tag_score:
            reason = "基于其他用户的共同互动"
        elif any(tag.id in explicit_styles for tag in artwork.tags) and tag_score > 0:
            reason = "符合你偏好的风格"
        elif tag_score > 0:
            reason = "与浏览历史风格相近"
        else:
            reason = "编辑精选" if artwork.featured else "热门作品"
        scored.append((artwork, score, reason, evidence))
    scored.sort(
        key=lambda row: (row[0].id not in profile, row[1], row[0].created_at, row[0].id),
        reverse=True,
    )
    return {"kind": kind, "strategy": "hybrid" if profile else "preferences", "items": [
        _serialize(artwork, reason, evidence) for artwork, _, reason, evidence in scored[:limit]
    ]}
