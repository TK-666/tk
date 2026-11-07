import unittest
from io import BytesIO

from PIL import Image

from app import create_app
from app.extensions import db
from app.models import User


class SmokeTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-key", "SQLALCHEMY_DATABASE_URI": "sqlite://"})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        admin = User(username="admin", display_name="Admin", role="admin")
        admin.set_password("admin-password")
        db.session.add(admin)
        db.session.commit()
        self.admin = self.app.test_client()
        self.user = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_full_flow(self):
        self.assertEqual(self.admin.post("/api/auth/login", json={"username": "admin", "password": "admin-password"}).status_code, 200)
        tag = self.admin.post("/api/admin/tags", json={"name": "印象派", "category": "style"})
        self.assertEqual(tag.status_code, 201)
        tag_id = tag.json["item"]["id"]
        artwork = self.admin.post("/api/admin/artworks", json={"title": "日出", "artist": "示例画家", "status": "published", "tag_ids": [tag_id]})
        self.assertEqual(artwork.status_code, 201)
        artwork_id = artwork.json["item"]["id"]

        self.assertEqual(self.user.post("/api/auth/register", json={"username": "visitor", "password": "visitor-password"}).status_code, 201)
        self.assertEqual(self.user.put("/api/auth/preferences", json={"tag_ids": [tag_id]}).status_code, 200)
        self.assertEqual(self.user.get("/api/artworks", query_string={"style": tag_id}).json["total"], 1)
        self.assertEqual(self.user.get(f"/api/artworks/{artwork_id}").status_code, 200)
        self.assertEqual(self.user.put(f"/api/artworks/{artwork_id}/interaction", json={"action": "favorite", "active": True}).status_code, 200)
        self.assertEqual(len(self.user.get("/api/me/favorites").json["items"]), 1)
        self.assertEqual(self.user.get("/api/recommendations?kind=personal").json["items"][0]["id"], artwork_id)
        self.assertEqual(self.admin.get("/api/admin/stats").json["views"], 1)
        self.assertEqual(self.user.post("/api/admin/tags", json={"name": "x", "category": "style"}).status_code, 403)

    def test_admin_upload_tag_cleanup_and_disabled_user(self):
        self.admin.post("/api/auth/login", json={"username": "admin", "password": "admin-password"})
        image = Image.new("RGB", (2, 2), "white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        response = self.admin.post("/api/admin/uploads", data={"file": (buffer, "sample.png")})
        self.assertEqual(response.status_code, 201)
        with self.admin.get(response.json["url"]) as uploaded:
            self.assertEqual(uploaded.status_code, 200)
            uploaded.close()

        tag_id = self.admin.post("/api/admin/tags", json={"name": "水彩", "category": "style"}).json["item"]["id"]
        artwork_id = self.admin.post("/api/admin/artworks", json={"title": "画", "status": "published", "tag_ids": [tag_id]}).json["item"]["id"]
        self.user.post("/api/auth/register", json={"username": "visitor", "password": "visitor-password"})
        self.user.put("/api/auth/preferences", json={"tag_ids": [tag_id]})
        self.assertEqual(self.admin.delete(f"/api/admin/tags/{tag_id}").status_code, 200)
        self.assertEqual(self.user.get(f"/api/artworks/{artwork_id}").json["item"]["tags"], [])
        user_id = self.user.get("/api/auth/me").json["user"]["id"]
        self.assertEqual(self.admin.patch(f"/api/admin/users/{user_id}", json={"enabled": False}).status_code, 200)
        self.assertEqual(self.user.get("/api/me/favorites").status_code, 401)


if __name__ == "__main__":
    unittest.main()
