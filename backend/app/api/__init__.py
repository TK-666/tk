from flask import Blueprint, jsonify

api = Blueprint("api", __name__)


@api.get("/health")
def health():
    return jsonify(status="ok")


from . import admin, artworks, auth, interactions, recommendations  # noqa: E402,F401
