from functools import wraps

from flask import abort, request, session

from ..extensions import db
from ..models import User


def payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="请求体必须是 JSON 对象")
    return data


def current_user():
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    return user if user and user.enabled else None


def require_user(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            abort(401, description="请先登录")
        return view(*args, **kwargs)

    return wrapped


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            abort(401, description="请先登录")
        if user.role != "admin":
            abort(403, description="需要管理员权限")
        return view(*args, **kwargs)

    return wrapped


def integer(value, name, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        abort(400, description=f"{name} 必须是整数")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        abort(400, description=f"{name} 必须是整数")
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        abort(400, description=f"{name} 超出范围")
    return number
