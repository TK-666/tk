from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
import warnings

from flask import abort, current_app, jsonify, request, send_from_directory
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import or_

from ..extensions import db
from ..models import Artwork, BehaviorLog, RecommendationSetting, Tag, User, artwork_tags, user_preferences
from . import api
from .common import current_user, integer, payload, require_admin


TAG_CATEGORIES = ("style", "topic", "medium", "era")
ARTWORK_STATUSES = ("draft", "published", "archived")


def _valid_image_url(value):
    if not value:
        return True
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return True
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.hostname) and not parsed.username and not parsed.password


def _artwork_fields(artwork, data):
    for field in ("title", "artist", "artist_bio", "description", "cover_url", "image_url"):
        if field in data:
            if not isinstance(data[field], str):
                abort(400, description=f"{field} 必须是文本")
            value = data[field].strip()
            if len(value) > {"title": 160, "artist": 120, "cover_url": 500, "image_url": 500}.get(field, 20000):
                abort(400, description=f"{field} 过长")
            if field in ("cover_url", "image_url") and not _valid_image_url(value):
                abort(400, description=f"{field} 必须是 HTTP(S) 或站内路径")
            setattr(artwork, field, value)
    if not artwork.title:
        abort(400, description="作品标题不能为空")
    if "status" in data:
        if data["status"] not in ARTWORK_STATUSES:
            abort(400, description="status 不合法")
        artwork.status = data["status"]
    if artwork.status == "published" and not artwork.image_url:
        abort(400, description="发布前请上传原图")
    if "featured" in data:
        if not isinstance(data["featured"], bool):
            abort(400, description="featured 必须为布尔值")
        artwork.featured = data["featured"]
    if "tag_ids" in data:
        if not isinstance(data["tag_ids"], list) or len(data["tag_ids"]) > 30:
            abort(400, description="tag_ids 必须为不超过 30 项的数组")
        ids = {integer(item, "标签 ID", 1) for item in data["tag_ids"]}
        tags = db.session.scalars(db.select(Tag).where(Tag.id.in_(ids))).all()
        if len(tags) != len(ids):
            abort(400, description="包含不存在的标签")
        artwork.tags = tags


@api.get("/admin/artworks")
@require_admin
def admin_artworks():
    page = integer(request.args.get("page", 1), "page", 1)
    per_page = integer(request.args.get("per_page", 20), "per_page", 1, 100)
    status = request.args.get("status", "")
    if status and status not in ARTWORK_STATUSES:
        abort(400, description="status 不合法")
    query = db.select(Artwork)
    if status:
        query = query.where(Artwork.status == status)
    keyword = request.args.get("q", "").strip()
    if keyword:
        if len(keyword) > 100:
            abort(400, description="搜索词过长")
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        query = query.where(or_(Artwork.title.ilike(like, escape="\\"), Artwork.artist.ilike(like, escape="\\")))
    total = db.session.scalar(db.select(db.func.count()).select_from(query.subquery()))
    items = db.session.scalars(query.order_by(Artwork.created_at.desc(), Artwork.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    return jsonify(items=[item.to_dict() for item in items], total=total, page=page, per_page=per_page)


@api.get("/admin/artworks/<int:artwork_id>")
@require_admin
def admin_artwork(artwork_id):
    artwork = db.session.get(Artwork, artwork_id)
    if not artwork:
        abort(404, description="作品不存在")
    return jsonify(item=artwork.to_dict())


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
    name = data.get("name")
    if not isinstance(name, str):
        abort(400, description="标签名称或类别不合法")
    name = name.strip()
    category = data.get("category")
    if not name or len(name) > 60 or category not in TAG_CATEGORIES:
        abort(400, description="标签名称或类别不合法")
    if db.session.scalar(db.select(Tag).filter_by(name=name, category=category)):
        abort(409, description="同类别下该标签已存在")
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
        if not isinstance(data["name"], str):
            abort(400, description="标签名称不合法")
        name = data["name"].strip()
        if not name or len(name) > 60:
            abort(400, description="标签名称不合法")
        tag.name = name
    if "category" in data:
        if data["category"] not in TAG_CATEGORIES:
            abort(400, description="标签类别不合法")
        if tag.category == "style" and data["category"] != "style":
            used = db.session.scalar(db.select(user_preferences.c.user_id).where(user_preferences.c.tag_id == tag_id).limit(1))
            if used is not None:
                abort(409, description="该风格已被用户设为偏好，不能改为其他类别")
        tag.category = data["category"]
    duplicate = db.session.scalar(db.select(Tag).where(Tag.id != tag_id, Tag.name == tag.name, Tag.category == tag.category))
    if duplicate:
        abort(409, description="同类别下该标签已存在")
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
        password = data["password"]
        if not isinstance(password, str) or not 8 <= len(password) <= 128:
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
    purpose = request.form.get("purpose", "original")
    if purpose not in ("cover", "original"):
        abort(400, description="purpose 必须是 cover 或 original")
    raw = file.read()
    if not raw:
        abort(400, description="图片文件为空")
    written = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                if source.format not in ("JPEG", "PNG", "WEBP"):
                    abort(400, description="仅支持 JPEG、PNG、WebP")
                if source.width * source.height > 40_000_000 or max(source.size) > 12_000:
                    abort(400, description="图片像素过大")
                source.load()
                original_format = source.format
                image = ImageOps.exif_transpose(source)
        upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
        stem = uuid4().hex
        if purpose == "original":
            suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[original_format]
            original_name = f"{stem}{suffix}"
            original_path = upload_dir / original_name
            written.append(original_path)
            original_path.write_bytes(raw)
        cover_name = f"{stem}-cover.webp"
        cover_path = upload_dir / cover_name
        written.append(cover_path)
        image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            image = image.convert("RGBA")
        else:
            image = image.convert("RGB")
        image.save(cover_path, format="WEBP", quality=82, method=6)
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError):
        for path in written:
            path.unlink(missing_ok=True)
        abort(400, description="图片格式无效")
    if purpose == "original":
        return jsonify(url=f"/api/uploads/{original_name}", cover_url=f"/api/uploads/{cover_name}"), 201
    return jsonify(url=f"/api/uploads/{cover_name}"), 201


@api.get("/uploads/<path:name>")
def serve_upload(name):
    mimetype = "image/webp" if Path(name).suffix.lower() == ".webp" else None
    response = send_from_directory(current_app.config["UPLOAD_FOLDER"], name, max_age=31536000, mimetype=mimetype)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
