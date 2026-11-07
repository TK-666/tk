from flask import abort, jsonify, session

from ..extensions import db
from ..models import Tag, User
from . import api
from .common import current_user, integer, payload, require_user


@api.post("/auth/register")
def register():
    data = payload()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not 3 <= len(username) <= 50 or not 8 <= len(password) <= 128:
        abort(400, description="用户名需为 3–50 字符，密码需为 8–128 字符")
    if db.session.scalar(db.select(User).filter_by(username=username)):
        abort(409, description="用户名已存在")
    user = User(username=username, display_name=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    session.clear()
    session["user_id"] = user.id
    return jsonify(user=user.to_dict()), 201


@api.post("/auth/login")
def login():
    data = payload()
    user = db.session.scalar(db.select(User).filter_by(username=str(data.get("username", "")).strip()))
    if not user or not user.enabled or not user.check_password(str(data.get("password", ""))):
        abort(401, description="用户名或密码错误，或账号已禁用")
    session.clear()
    session["user_id"] = user.id
    return jsonify(user=user.to_dict())


@api.post("/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@api.get("/auth/me")
@require_user
def me():
    return jsonify(user=current_user().to_dict())


@api.patch("/auth/me")
@require_user
def update_me():
    data = payload()
    user = current_user()
    tags = _style_tags(data["tag_ids"]) if "tag_ids" in data else None
    if "display_name" in data:
        name = str(data["display_name"]).strip()
        if len(name) > 80:
            abort(400, description="昵称过长")
    if "password" in data:
        password = str(data["password"])
        if not 8 <= len(password) <= 128:
            abort(400, description="密码需为 8–128 字符")
        if not user.check_password(str(data.get("current_password", ""))):
            abort(400, description="当前密码错误")
        user.set_password(password)
    if "display_name" in data:
        user.display_name = name
    if tags is not None:
        user.preferences = tags
    db.session.commit()
    return jsonify(user=user.to_dict())


@api.put("/auth/preferences")
@require_user
def set_preferences():
    user = current_user()
    user.preferences = _style_tags(payload().get("tag_ids"))
    db.session.commit()
    return jsonify(user=user.to_dict())


def _style_tags(ids):
    if not isinstance(ids, list) or len(ids) > 30:
        abort(400, description="tag_ids 必须为不超过 30 项的数组")
    selected = {integer(item, "标签 ID", 1) for item in ids}
    tags = db.session.scalars(db.select(Tag).where(Tag.id.in_(selected), Tag.category == "style")).all()
    if len(tags) != len(selected):
        abort(400, description="只能选择存在的风格标签")
    return tags
