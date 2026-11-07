import unittest
from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image

from app import create_app
from app.extensions import db
from app.models import BehaviorLog, User


class SmokeTest(unittest.TestCase):
    def setUp(self):
        self.uploads = TemporaryDirectory()
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-key", "SQLALCHEMY_DATABASE_URI": "sqlite://", "UPLOAD_FOLDER": self.uploads.name})
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
        self.uploads.cleanup()

    def test_full_flow(self):
        self.assertEqual(self.admin.post("/api/auth/login", json={"username": "admin", "password": "admin-password"}).status_code, 200)
        tag = self.admin.post("/api/admin/tags", json={"name": "印象派", "category": "style"})
        self.assertEqual(tag.status_code, 201)
        tag_id = tag.json["item"]["id"]
        artwork = self.admin.post("/api/admin/artworks", json={"title": "日出", "artist": "示例画家", "image_url": "https://example.test/art.jpg", "status": "published", "tag_ids": [tag_id]})
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

    def test_separate_tab_sessions_and_logout(self):
        client = self.app.test_client()
        admin_tab = {"X-Tab-Session": "a" * 32}
        user_tab = {"X-Tab-Session": "b" * 32}
        self.assertEqual(client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin-password'}, headers=admin_tab).status_code, 200)
        self.assertEqual(client.post('/api/auth/register', json={'username': 'visitor', 'password': 'visitor-password'}, headers=user_tab).status_code, 201)
        self.assertEqual(client.get('/api/auth/me', headers=admin_tab).json['user']['role'], 'admin')
        self.assertEqual(client.get('/api/admin/stats', headers=user_tab).status_code, 403)
        self.assertEqual(client.get('/api/admin/stats', headers=admin_tab).status_code, 200)
        client.post('/api/auth/logout', headers=user_tab)
        self.assertEqual(client.get('/api/auth/me', headers=user_tab).status_code, 401)
        self.assertEqual(client.get('/api/admin/stats', headers=admin_tab).status_code, 200)

    def test_profile_and_favorite_removal(self):
        self.admin.post("/api/auth/login", json={"username": "admin", "password": "admin-password"})
        tag = self.admin.post("/api/admin/tags", json={"name": "水墨", "category": "style"}).json["item"]
        artwork = self.admin.post("/api/admin/artworks", json={"title": "山川", "image_url": "https://example.test/art.jpg", "status": "published"}).json["item"]
        self.user.post("/api/auth/register", json={"username": "visitor", "password": "visitor-password"})

        profile = self.user.patch("/api/auth/me", json={"display_name": "山水", "tag_ids": [tag["id"]]})
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json["user"]["preference_tag_ids"], [tag["id"]])
        rejected = self.user.patch("/api/auth/me", json={"display_name": "不应保存", "tag_ids": [99999]})
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(self.user.get("/api/auth/me").json["user"]["display_name"], "山水")

        url = f'/api/artworks/{artwork["id"]}/interaction'
        for active in (True, True, False, False):
            response = self.user.put(url, json={"action": "favorite", "active": active})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["favorited"], active)
        self.assertEqual(self.user.get("/api/me/favorites").json["items"], [])
        for score in (True, 2.5):
            self.assertEqual(self.user.put(url, json={"action": "rate", "score": score}).status_code, 400)
        events = db.session.scalars(db.select(BehaviorLog.action).order_by(BehaviorLog.id)).all()
        self.assertEqual(events, ["favorite", "unfavorite"])

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
        self.assertEqual(self.admin.post("/api/admin/uploads", data={"file": (BytesIO(b"not an image"), "bad.png")}).status_code, 400)

        tag_id = self.admin.post("/api/admin/tags", json={"name": "水彩", "category": "style"}).json["item"]["id"]
        self.assertEqual(self.admin.patch(f"/api/admin/tags/{tag_id}", json={"name": "现代水彩"}).json["item"]["name"], "现代水彩")
        artwork_id = self.admin.post("/api/admin/artworks", json={"title": "画", "image_url": "https://example.test/art.jpg", "status": "published", "tag_ids": [tag_id]}).json["item"]["id"]
        self.user.post("/api/auth/register", json={"username": "visitor", "password": "visitor-password"})
        self.user.put("/api/auth/preferences", json={"tag_ids": [tag_id]})
        self.assertEqual(self.admin.delete(f"/api/admin/tags/{tag_id}").status_code, 200)
        self.assertEqual(self.user.get(f"/api/artworks/{artwork_id}").json["item"]["tags"], [])
        user_id = self.user.get("/api/auth/me").json["user"]["id"]
        self.assertEqual(self.admin.patch("/api/admin/users/1", json={"enabled": False}).status_code, 400)
        self.assertEqual(self.admin.patch(f"/api/admin/users/{user_id}", json={"password": "reset-password"}).status_code, 200)
        self.assertEqual(self.admin.patch(f"/api/admin/users/{user_id}", json={"enabled": False}).status_code, 200)
        self.assertEqual(self.user.get("/api/me/favorites").status_code, 401)

    def test_catalog_filters_and_publication(self):
        self.admin.post("/api/auth/login", json={"username": "admin", "password": "admin-password"})
        tags = {}
        for category, name in (("style", "国风"), ("topic", "山水"), ("medium", "水彩"), ("era", "现代")):
            tags[category] = self.admin.post("/api/admin/tags", json={"name": name, "category": category}).json["item"]["id"]
        artwork_id = self.admin.post("/api/admin/artworks", json={
            "title": "青山", "artist": "测试作者", "tag_ids": list(tags.values()),
        }).json["item"]["id"]
        self.assertEqual(self.user.get("/api/artworks").json["total"], 0)
        self.assertEqual(self.user.get(f"/api/artworks/{artwork_id}").status_code, 404)
        self.assertEqual(self.admin.patch(f"/api/admin/artworks/{artwork_id}", json={"status": "published", "image_url": "https://example.test/art.jpg"}).status_code, 200)
        for category, tag_id in tags.items():
            self.assertEqual(self.user.get("/api/artworks", query_string={category: tag_id, "q": "青山"}).json["total"], 1)
        self.assertEqual(self.user.get("/api/artworks", query_string={"q": "测试作者"}).json["total"], 1)
        self.assertEqual(self.user.get("/api/artworks", query_string={"q": "不存在"}).json["total"], 0)
        self.assertEqual(self.user.get("/api/artworks", query_string={"page": 0}).status_code, 400)
        self.assertEqual(self.admin.patch(f"/api/admin/artworks/{artwork_id}", json={"status": "archived"}).status_code, 200)
        self.assertEqual(self.user.get("/api/artworks").json["total"], 0)
        self.assertEqual(self.user.get(f"/api/artworks/{artwork_id}/interaction").status_code, 401)

    def test_interactions_recommendations_and_settings(self):
        self.admin.post("/api/auth/login", json={"username": "admin", "password": "admin-password"})
        tag_id = self.admin.post("/api/admin/tags", json={"name": "抽象", "category": "style"}).json["item"]["id"]
        artwork_ids = [self.admin.post("/api/admin/artworks", json={"title": title, "image_url": "https://example.test/art.jpg", "status": "published", "tag_ids": tags}).json["item"]["id"]
                       for title, tags in (("甲", [tag_id]), ("乙", [tag_id]), ("丙", []))]
        self.user.post("/api/auth/register", json={"username": "visitor", "password": "visitor-password"})
        self.user.put("/api/auth/preferences", json={"tag_ids": [tag_id]})
        self.assertEqual(self.user.get(f"/api/artworks/{artwork_ids[0]}/interaction").json["rating"], None)
        self.assertEqual(self.user.put(f"/api/artworks/{artwork_ids[0]}/interaction", json={"action": "rate", "score": 5}).json["rating"], 5)
        self.assertTrue(self.user.put(f"/api/artworks/{artwork_ids[0]}/interaction", json={"action": "like", "active": True}).json["liked"])
        self.assertFalse(self.user.put(f"/api/artworks/{artwork_ids[0]}/interaction", json={"action": "like", "active": False}).json["liked"])
        self.assertEqual(self.user.put(f"/api/artworks/{artwork_ids[0]}/interaction", json={"action": "rate", "score": 6}).status_code, 400)
        self.assertEqual(self.user.get("/api/recommendations?kind=personal").json["items"][0]["id"], artwork_ids[1])
        self.assertEqual(len(self.user.get("/api/recommendations?kind=hot").json["items"]), 3)
        self.assertEqual(self.user.get("/api/recommendations?kind=latest").json["items"][0]["id"], artwork_ids[2])
        self.assertEqual(self.user.get("/api/recommendations?kind=invalid").status_code, 400)
        self.assertEqual(self.admin.put("/api/admin/settings", json={"tag_weight": 8, "itemcf_weight": 4}).status_code, 200)
        self.assertEqual(self.admin.get("/api/admin/settings").json["items"]["tag_weight"], "8.0")
        self.assertEqual(self.admin.put("/api/admin/settings", json={"tag_weight": -1}).status_code, 400)

    def test_account_validation_and_password_update(self):
        self.assertEqual(self.user.post("/api/auth/register", json={"username": "ab", "password": "short"}).status_code, 400)
        self.assertEqual(self.user.post("/api/auth/register", json={"username": "visitor", "password": "visitor-password"}).status_code, 201)
        self.assertEqual(self.admin.post("/api/auth/register", json={"username": "visitor", "password": "visitor-password"}).status_code, 409)
        self.assertEqual(self.user.patch("/api/auth/me", json={"display_name": "新名字"}).json["user"]["display_name"], "新名字")
        self.assertEqual(self.user.patch("/api/auth/me", json={"password": "new-password"}).status_code, 400)
        self.assertEqual(self.user.patch("/api/auth/me", json={"current_password": "visitor-password", "password": "new-password"}).status_code, 200)
        self.assertEqual(self.user.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.user.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.user.post("/api/auth/login", json={"username": "visitor", "password": "visitor-password"}).status_code, 401)
        self.assertEqual(self.user.post("/api/auth/login", json={"username": "visitor", "password": "new-password"}).status_code, 200)

    def test_itemcf_weight_changes_personal_order(self):
        self.admin.post("/api/auth/login", json={"username": "admin", "password": "admin-password"})
        source = self.admin.post("/api/admin/artworks", json={"title": "共同收藏", "image_url": "https://example.test/art.jpg", "status": "published"}).json["item"]["id"]
        collaborative = self.admin.post("/api/admin/artworks", json={"title": "协同候选", "image_url": "https://example.test/art.jpg", "status": "published"}).json["item"]["id"]
        featured = self.admin.post("/api/admin/artworks", json={"title": "置顶候选", "image_url": "https://example.test/art.jpg", "status": "published", "featured": True}).json["item"]["id"]
        peer = self.app.test_client()
        peer.post("/api/auth/register", json={"username": "peer", "password": "peer-password"})
        peer.put(f"/api/artworks/{source}/interaction", json={"action": "favorite", "active": True})
        peer.put(f"/api/artworks/{collaborative}/interaction", json={"action": "favorite", "active": True})
        self.user.post("/api/auth/register", json={"username": "visitor", "password": "visitor-password"})
        self.user.put(f"/api/artworks/{source}/interaction", json={"action": "favorite", "active": True})
        self.admin.put("/api/admin/settings", json={"tag_weight": 0, "itemcf_weight": 0})
        self.assertEqual(self.user.get("/api/recommendations?kind=personal").json["items"][0]["id"], featured)
        self.admin.put("/api/admin/settings", json={"itemcf_weight": 10})
        self.assertEqual(self.user.get("/api/recommendations?kind=personal").json["items"][0]["id"], collaborative)


if __name__ == "__main__":
    unittest.main()
