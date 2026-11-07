import unittest
from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image

from app import create_app
from app.extensions import db
from app.models import User


class ArtworksTagsTest(unittest.TestCase):
    def setUp(self):
        self.uploads = TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "catalog-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "UPLOAD_FOLDER": self.uploads.name,
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        admin = User(username="admin", display_name="Admin", role="admin")
        admin.set_password("admin-password")
        db.session.add(admin)
        db.session.commit()
        self.admin = self.app.test_client()
        self.visitor = self.app.test_client()
        self.admin.post("/api/auth/login", json={"username": "admin", "password": "admin-password"})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.uploads.cleanup()

    def artwork(self, title, **fields):
        data = {"title": title, "image_url": "https://example.test/original.jpg", "status": "published", **fields}
        response = self.admin.post("/api/admin/artworks", json=data)
        self.assertEqual(response.status_code, 201, response.json)
        return response.json["item"]["id"]

    def test_publish_requires_original_and_safe_url(self):
        response = self.admin.post("/api/admin/artworks", json={"title": "未配图", "status": "published"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.visitor.get("/api/artworks").json["total"], 0)
        self.assertEqual(self.admin.post("/api/admin/artworks", json={"title": "危险链接", "image_url": "javascript:alert(1)"}).status_code, 400)
        draft_id = self.admin.post("/api/admin/artworks", json={"title": "草稿"}).json["item"]["id"]
        self.assertEqual(self.admin.patch(f"/api/admin/artworks/{draft_id}", json={"status": "published"}).status_code, 400)
        self.assertEqual(self.admin.patch(f"/api/admin/artworks/{draft_id}", json={"image_url": "/api/uploads/example.jpg", "status": "published"}).status_code, 200)
        self.assertEqual(self.visitor.get("/api/artworks").json["total"], 1)

    def test_category_filter_and_literal_search(self):
        style = self.admin.post("/api/admin/tags", json={"name": "国风", "category": "style"}).json["item"]["id"]
        topic = self.admin.post("/api/admin/tags", json={"name": "人物", "category": "topic"}).json["item"]["id"]
        self.artwork("作品%一", tag_ids=[topic])
        self.artwork("作品二", tag_ids=[style])
        self.assertEqual(self.visitor.get("/api/artworks", query_string={"style": topic}).json["total"], 0)
        self.assertEqual(self.visitor.get("/api/artworks", query_string={"topic": topic}).json["total"], 1)
        self.assertEqual(self.visitor.get("/api/artworks", query_string={"q": "%"}).json["total"], 1)
        self.assertEqual(self.visitor.get("/api/artworks", query_string={"q": "_"}).json["total"], 0)
        self.assertEqual(self.visitor.get("/api/tags?category=unknown").status_code, 400)

    def test_admin_pagination_and_tag_rules(self):
        self.assertEqual(self.visitor.get("/api/admin/artworks").status_code, 401)
        for number in range(22):
            self.artwork(f"测试作品{number:02d}", status="draft" if number % 2 else "published")
        page1 = self.admin.get("/api/admin/artworks?page=1&per_page=20").json
        page2 = self.admin.get("/api/admin/artworks?page=2&per_page=20").json
        self.assertEqual((page1["total"], len(page1["items"]), len(page2["items"])), (22, 20, 2))
        self.assertEqual(self.admin.get("/api/admin/artworks?status=published").json["total"], 11)
        self.assertEqual(self.admin.get("/api/admin/artworks?q=测试作品03").json["total"], 1)
        artwork_id = page1["items"][0]["id"]
        self.assertEqual(self.admin.get(f"/api/admin/artworks/{artwork_id}").json["item"]["id"], artwork_id)
        self.assertEqual(self.admin.get("/api/admin/artworks?per_page=101").status_code, 400)
        tag = self.admin.post("/api/admin/tags", json={"name": "印象派", "category": "style"}).json["item"]
        self.assertEqual(self.admin.post("/api/admin/tags", json={"name": "印象派", "category": "style"}).status_code, 409)
        self.visitor.post("/api/auth/register", json={"username": "visitor", "password": "visitor-password"})
        self.visitor.put("/api/auth/preferences", json={"tag_ids": [tag["id"]]})
        self.assertEqual(self.admin.patch(f"/api/admin/tags/{tag['id']}", json={"category": "topic"}).status_code, 409)

    def test_original_upload_generates_small_cover(self):
        image = Image.new("RGB", (1800, 900), "navy")
        file = BytesIO()
        image.save(file, format="PNG")
        source = file.getvalue()
        response = self.admin.post("/api/admin/uploads", data={"file": (BytesIO(source), "image.png"), "purpose": "original"})
        self.assertEqual(response.status_code, 201, response.json)
        self.assertIn("cover_url", response.json)
        with self.admin.get(response.json["url"]) as original:
            self.assertEqual(original.data, source)
            original.close()
        with self.admin.get(response.json["cover_url"]) as cover:
            self.assertEqual(cover.mimetype, "image/webp")
            self.assertEqual(cover.headers["X-Content-Type-Options"], "nosniff")
            with Image.open(BytesIO(cover.data)) as thumbnail:
                self.assertLessEqual(max(thumbnail.size), 1200)
                self.assertEqual(thumbnail.format, "WEBP")
            cover.close()
        self.assertEqual(self.admin.post("/api/admin/uploads", data={"file": (BytesIO(source), "image.png"), "purpose": "other"}).status_code, 400)
        very_wide = Image.new("RGB", (12001, 1), "white")
        file = BytesIO()
        very_wide.save(file, format="PNG")
        self.assertEqual(self.admin.post("/api/admin/uploads", data={"file": (BytesIO(file.getvalue()), "wide.png")}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
