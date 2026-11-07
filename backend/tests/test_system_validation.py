"""Regression checks for account and tag input validation."""

import unittest
from tempfile import TemporaryDirectory

from app import create_app
from app.extensions import db
from app.models import Tag, User


class SystemValidationTest(unittest.TestCase):
    def setUp(self):
        self.uploads = TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "system-validation",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "UPLOAD_FOLDER": self.uploads.name,
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        admin = User(username="admin", role="admin")
        admin.set_password("admin-password")
        db.session.add_all([admin, Tag(name="印象派", category="style")])
        db.session.commit()
        self.tag_id = db.session.scalar(db.select(Tag.id))
        self.admin = self.app.test_client()
        self.admin.post("/api/auth/login", json={"username": "admin", "password": "admin-password"})
        self.visitor = self.app.test_client()
        self.visitor.post("/api/auth/register", json={"username": "visitor", "password": "visitor-password"})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.uploads.cleanup()

    def test_non_text_credentials_are_rejected(self):
        for username, password in ((None, "valid-password"), ("newuser", ["long-password"]), ("otheruser", 12345678)):
            with self.subTest(username=username, password=password):
                response = self.app.test_client().post("/api/auth/register", json={"username": username, "password": password})
                self.assertEqual(response.status_code, 400)
        response = self.visitor.patch("/api/auth/me", json={"current_password": "visitor-password", "password": ["new-password"]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.app.test_client().post("/api/auth/login", json={"username": "visitor", "password": "visitor-password"}).status_code, 200)
        user_id = self.visitor.get("/api/auth/me").json["user"]["id"]
        self.assertEqual(self.admin.patch(f"/api/admin/users/{user_id}", json={"password": 12345678}).status_code, 400)

    def test_tag_ids_reject_boolean_and_fractional_values(self):
        for invalid in (True, self.tag_id + 0.5):
            with self.subTest(value=invalid):
                response = self.visitor.put("/api/auth/preferences", json={"tag_ids": [invalid]})
                self.assertEqual(response.status_code, 400)
                response = self.admin.post("/api/admin/artworks", json={"title": "测试", "tag_ids": [invalid]})
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.visitor.get("/api/auth/me").json["user"]["preference_tag_ids"], [])
        self.assertEqual(self.visitor.put("/api/auth/preferences", json={"tag_ids": [self.tag_id]}).status_code, 200)

    def test_non_text_names_are_rejected(self):
        self.assertEqual(self.visitor.patch("/api/auth/me", json={"display_name": None}).status_code, 400)
        self.assertEqual(self.admin.post("/api/admin/tags", json={"name": None, "category": "style"}).status_code, 400)
        self.assertEqual(self.admin.patch(f"/api/admin/tags/{self.tag_id}", json={"name": ["错误"]}).status_code, 400)
        self.assertEqual(self.admin.get("/api/tags?category=style").json["items"][0]["name"], "印象派")


if __name__ == "__main__":
    unittest.main()
