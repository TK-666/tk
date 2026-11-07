from flask import abort, jsonify, request

from ..services.recommendation import recommend
from . import api
from .common import current_user, integer


@api.get("/recommendations")
def recommendations():
    kind = request.args.get("kind", "personal")
    if kind not in ("personal", "hot", "latest"):
        abort(400, description="kind 必须是 personal、hot 或 latest")
    limit = integer(request.args.get("limit", 20), "limit", 1, 50)
    return jsonify(recommend(kind, current_user(), limit))
