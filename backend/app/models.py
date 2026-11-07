from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


artwork_tags = db.Table(
    "artwork_tags",
    db.Column("artwork_id", db.Integer, db.ForeignKey("artworks.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), primary_key=True),
)

user_preferences = db.Table(
    "user_preferences",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), primary_key=True),
)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(80), nullable=False, default="")
    role = db.Column(db.String(20), nullable=False, default="user")
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    preferences = db.relationship("Tag", secondary=user_preferences, lazy="selectin")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id, "username": self.username,
            "display_name": self.display_name, "role": self.role,
            "enabled": self.enabled,
            "preference_tag_ids": [tag.id for tag in self.preferences],
        }


class Tag(db.Model):
    __tablename__ = "tags"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False)
    category = db.Column(db.String(20), nullable=False)  # style, topic, medium, era
    __table_args__ = (db.UniqueConstraint("name", "category"),)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "category": self.category}


class Artwork(db.Model):
    __tablename__ = "artworks"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False, index=True)
    artist = db.Column(db.String(120), nullable=False, default="")
    artist_bio = db.Column(db.Text, nullable=False, default="")
    description = db.Column(db.Text, nullable=False, default="")
    cover_url = db.Column(db.String(500), nullable=False, default="")
    image_url = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="draft")
    featured = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    tags = db.relationship("Tag", secondary=artwork_tags, lazy="selectin")

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "artist": self.artist,
            "artist_bio": self.artist_bio, "description": self.description,
            "cover_url": self.cover_url, "image_url": self.image_url,
            "status": self.status, "featured": self.featured,
            "created_at": self.created_at.isoformat(),
            "tags": [tag.to_dict() for tag in self.tags],
        }


class Favorite(db.Model):
    __tablename__ = "favorites"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    artwork_id = db.Column(db.Integer, db.ForeignKey("artworks.id"), primary_key=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class Like(db.Model):
    __tablename__ = "likes"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    artwork_id = db.Column(db.Integer, db.ForeignKey("artworks.id"), primary_key=True)


class Rating(db.Model):
    __tablename__ = "ratings"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    artwork_id = db.Column(db.Integer, db.ForeignKey("artworks.id"), primary_key=True)
    score = db.Column(db.Integer, nullable=False)


class BehaviorLog(db.Model):
    __tablename__ = "behavior_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    artwork_id = db.Column(db.Integer, db.ForeignKey("artworks.id"), nullable=False, index=True)
    action = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)


class RecommendationSetting(db.Model):
    __tablename__ = "recommendation_settings"
    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.String(100), nullable=False)
