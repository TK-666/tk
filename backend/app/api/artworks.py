from flask import abort, jsonify, request
from sqlalchemy import or_

from ..extensions import db
from ..models import Artwork, BehaviorLog, Tag
from . import api
from .common import current_user, integer


@api.get("/tags")
def list_tags():
    category = request.args.get("category")
    query = db.select(Tag).order_by(Tag.category, Tag.name)
    if category:
        query = query.where(Tag.category == category)
    return jsonify(items=[item.to_dict() for item in db.session.scalars(query)])


@api.get("/artworks")
def list_artworks():
    page = integer(request.args.get("page", 1), "page", 1)
    per_page = integer(request.args.get("per_page", 12), "per_page", 1, 50)
    query = db.select(Artwork).where(Artwork.status == "published")
    keyword = request.args.get("q", "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.where(or_(Artwork.title.ilike(like), Artwork.artist.ilike(like)))
    for category in ("style", "topic", "medium", "era"):
        tag_id = request.args.get(category)
        if tag_id:
            query = query.where(Artwork.tags.any(Tag.id == integer(tag_id, category, 1)))
    count = db.session.scalar(db.select(db.func.count()).select_from(query.subquery()))
    items = db.session.scalars(query.order_by(Artwork.created_at.desc(), Artwork.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    return jsonify(items=[item.to_dict() for item in items], total=count, page=page, per_page=per_page)


@api.get("/artworks/<int:artwork_id>")
def get_artwork(artwork_id):
    artwork = db.session.get(Artwork, artwork_id)
    if not artwork or artwork.status != "published":
        abort(404, description="作品不存在")
    user = current_user()
    if user:
        db.session.add(BehaviorLog(user_id=user.id, artwork_id=artwork.id, action="view"))
        db.session.commit()
    return jsonify(item=artwork.to_dict())
