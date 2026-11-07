from io import BytesIO
from pathlib import Path
from uuid import uuid4

from flask import abort, current_app, jsonify, request, send_from_directory
from PIL import Image, UnidentifiedImageError

from ..extensions import db
from ..models import Artwork, BehaviorLog, RecommendationSetting, Tag, User
from . import api
from .common import current_user, integer, payload, require_admin
from ..models import artwork_tags, user_preferences


def _artwork_fields(artwork, data):
    for field in ("title", "artist", "artist_bio", "description", "cover_url", "image_url"):
        if field in data:
            value = str(data[field]).strip()
            if len(value) > {"title": 160, "artist": 120, "cover_url": 500, "image_url": 500}.get(field, 20000):
                abort(400, description=f"{field} 过长")
            setattr(artwork, field, value)
    if not artwork.title:
        abort(400, description="作品标题不能为空")
    if "status" in data:
        if data["status"] not in ("draft", "published", "archived"):
            abort(400, description="status 不合法")
        artwork.status = data["status"]
    if "featured" in data:
        if not isinstance(data["featured"], bool):
            abort(400, description="featured 必须为布尔值")
        artwork.featured = data["featured"]
    if "tag_ids" in data:
        if not isinstance(data["tag_ids"], list):
            abort(400, description="tag_ids 必须为数组")
        ids = {integer(item, "标签 ID", 1) for item in data["tag_ids"]}
        tags = db.session.scalars(db.select(Tag).where(Tag.id.in_(ids))).all()
        if len(tags) != len(ids):
            abort(400, description="包含不存在的标签")
        artwork.tags = tags


@api.get("/admin/artworks")
@require_admin
def admin_artworks():
    items = db.session.scalars(db.select(Artwork).order_by(Artwork.created_at.desc(), Artwork.id.desc())).all()
    return jsonify(items=[item.to_dict() for item in items])


@api.post("/admin/artworks")
@require_admin
def create_artwork():
    artwork = Artwork()
    _artwork_fields(artwork, payload())
    db.session.add(artwork)
    db.session.commit()
    return jsonify(item=artwork.to_dict()), 201


@api.patch("/admin/artworks/<int:artwork_id>")
@require_admin
def update_artwork(artwork_id):
    artwork = db.session.get(Artwork, artwork_id)
    if not artwork:
        abort(404, description="作品不存在")
    _artwork_fields(artwork, payload())
    db.session.commit()
    return jsonify(item=artwork.to_dict())


@api.post("/admin/tags")
@require_admin
def create_tag():
    data = payload()
    name = str(data.get("name", "")).strip()
    category = data.get("category")
    if not name or len(name) > 60 or category not in ("style", "topic", "medium", "era"):
        abort(400, description="标签名称或类别不合法")
    tag = Tag(name=name, category=category)
    db.session.add(tag)
    db.session.commit()
    return jsonify(item=tag.to_dict()), 201


@api.patch("/admin/tags/<int:tag_id>")
@require_admin
def update_tag(tag_id):
    tag = db.session.get(Tag, tag_id)
    if not tag:
        abort(404, description="标签不存在")
    data = payload()
    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 60:
            abort(400, description="标签名称不合法")
        tag.name = name
    if "category" in data:
        if data["category"] not in ("style", "topic", "medium", "era"):
            abort(400, description="标签类别不合法")
        tag.category = data["category"]
    db.session.commit()
    return jsonify(item=tag.to_dict())


@api.delete("/admin/tags/<int:tag_id>")
@require_admin
def delete_tag(tag_id):
    tag = db.session.get(Tag, tag_id)
    if not tag:
        abort(404, description="标签不存在")
    db.session.execute(db.delete(artwork_tags).where(artwork_tags.c.tag_id == tag_id))
    db.session.execute(db.delete(user_preferences).where(user_preferences.c.tag_id == tag_id))
    db.session.delete(tag)
    db.session.commit()
    return jsonify(ok=True)


@api.get("/admin/users")
@require_admin
def admin_users():
    users = db.session.scalars(db.select(User).order_by(User.id)).all()
    return jsonify(items=[user.to_dict() for user in users])


@api.patch("/admin/users/<int:user_id>")
@require_admin
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404, description="用户不存在")
    data = payload()
    if "enabled" in data:
        if not isinstance(data["enabled"], bool):
            abort(400, description="enabled 必须为布尔值")
        if user.id == current_user().id and not data["enabled"]:
            abort(400, description="不能禁用当前管理员账号")
        user.enabled = data["enabled"]
    if "password" in data:
        password = str(data["password"])
        if not 8 <= len(password) <= 128:
            abort(400, description="密码需为 8–128 字符")
        user.set_password(password)
    db.session.commit()
    return jsonify(user=user.to_dict())


@api.get("/admin/stats")
@require_admin
def stats():
    return jsonify(
        users=db.session.scalar(db.select(db.func.count(User.id))),
        artworks=db.session.scalar(db.select(db.func.count(Artwork.id))),
        published=db.session.scalar(db.select(db.func.count(Artwork.id)).where(Artwork.status == "published")),
        views=db.session.scalar(db.select(db.func.count(BehaviorLog.id)).where(BehaviorLog.action == "view")),
    )


@api.get("/admin/settings")
@require_admin
def settings():
    return jsonify(items={row.key: row.value for row in db.session.scalars(db.select(RecommendationSetting))})


@api.put("/admin/settings")
@require_admin
def update_settings():
    data = payload()
    for key in ("tag_weight", "itemcf_weight"):
        if key in data:
            try:
                value = float(data[key])
            except (TypeError, ValueError):
                abort(400, description=f"{key} 必须是数字")
            if not 0 <= value <= 100:
                abort(400, description=f"{key} 超出范围")
            row = db.session.get(RecommendationSetting, key)
            if not row:
                row = RecommendationSetting(key=key)
                db.session.add(row)
            row.value = str(value)
    db.session.commit()
    return settings()


@api.post("/admin/uploads")
@require_admin
def upload_image():
    file = request.files.get("file")
    if not file:
        abort(400, description="缺少图片文件")
    raw = file.read()
    try:
        image = Image.open(BytesIO(raw))
        image.verify()
        image = Image.open(BytesIO(raw))
        if image.format not in ("JPEG", "PNG", "WEBP"):
            abort(400, description="仅支持 JPEG、PNG、WebP")
        suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image.format]
        name = f"{uuid4().hex}{suffix}"
        image.save(Path(current_app.config["UPLOAD_FOLDER"]) / name)
    except (UnidentifiedImageError, OSError, ValueError):
        abort(400, description="图片格式无效")
    return jsonify(url=f"/api/uploads/{name}"), 201


@api.get("/uploads/<path:name>")
def serve_upload(name):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], name)
