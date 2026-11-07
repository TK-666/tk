from flask import abort, jsonify, request

from ..extensions import db
from ..models import Artwork, BehaviorLog, Favorite, Like, Rating
from . import api
from .common import current_user, integer, payload, require_user


@api.get("/me/favorites")
@require_user
def favorites():
    ids = db.session.scalars(
        db.select(Favorite.artwork_id).where(Favorite.user_id == current_user().id).order_by(Favorite.created_at.desc())
    ).all()
    artworks = {item.id: item for item in db.session.scalars(db.select(Artwork).where(Artwork.id.in_(ids), Artwork.status == "published"))}
    return jsonify(items=[artworks[item].to_dict() for item in ids if item in artworks])


@api.get("/artworks/<int:artwork_id>/interaction")
@require_user
def get_interaction(artwork_id):
    user_id = current_user().id
    rating = db.session.get(Rating, (user_id, artwork_id))
    return jsonify(
        liked=db.session.get(Like, (user_id, artwork_id)) is not None,
        favorited=db.session.get(Favorite, (user_id, artwork_id)) is not None,
        rating=rating.score if rating else None,
    )


@api.put("/artworks/<int:artwork_id>/interaction")
@require_user
def set_interaction(artwork_id):
    artwork = db.session.get(Artwork, artwork_id)
    if not artwork or artwork.status != "published":
        abort(404, description="作品不存在")
    data = payload()
    action = data.get("action")
    user_id = current_user().id
    if action in ("like", "favorite"):
        if not isinstance(data.get("active"), bool):
            abort(400, description="active 必须为布尔值")
        model = Like if action == "like" else Favorite
        existing = db.session.get(model, (user_id, artwork_id))
        if data["active"] and not existing:
            db.session.add(model(user_id=user_id, artwork_id=artwork_id))
        elif not data["active"] and existing:
            db.session.delete(existing)
    elif action == "rate":
        score = integer(data.get("score"), "score", 1, 5)
        existing = db.session.get(Rating, (user_id, artwork_id))
        if existing:
            existing.score = score
        else:
            db.session.add(Rating(user_id=user_id, artwork_id=artwork_id, score=score))
    else:
        abort(400, description="action 必须是 like、favorite 或 rate")
    db.session.add(BehaviorLog(user_id=user_id, artwork_id=artwork_id, action=action))
    db.session.commit()
    return get_interaction(artwork_id)
