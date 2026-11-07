import unittest

from app import create_app
from app.extensions import db
from app.models import Artwork, BehaviorLog, Favorite, Rating, RecommendationSetting, Tag, User


class RecommendationTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SECRET_KEY": "recommendation-test", "SQLALCHEMY_DATABASE_URI": "sqlite://"})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def user(self, name):
        user = User(username=name, display_name=name)
        user.set_password("test-password")
        db.session.add(user)
        db.session.flush()
        return user

    def artwork(self, title, tags=(), featured=False, status="published"):
        artwork = Artwork(title=title, tags=list(tags), featured=featured, status=status)
        db.session.add(artwork)
        db.session.flush()
        return artwork

    def client(self, user=None):
        client = self.app.test_client()
        if user:
            response = client.post("/api/auth/login", json={"username": user.username, "password": "test-password"})
            self.assertEqual(response.status_code, 200, response.json)
        return client

    def test_guest_hot_latest_limit_and_unpublished(self):
        popular = self.artwork("热门")
        featured = self.artwork("精选", featured=True)
        self.artwork("草稿", status="draft")
        visitor = self.user("visitor")
        db.session.add(Favorite(user_id=visitor.id, artwork_id=popular.id))
        db.session.commit()
        client = self.client()
        personal = client.get("/api/recommendations?kind=personal").json
        self.assertEqual(personal["strategy"], "guest_fallback")
        self.assertEqual([item["id"] for item in personal["items"]], [featured.id, popular.id])
        self.assertEqual(client.get("/api/recommendations?kind=hot").json["strategy"], "hot")
        self.assertEqual(client.get("/api/recommendations?kind=latest").json["items"][0]["id"], featured.id)
        self.assertEqual(len(client.get("/api/recommendations?limit=1").json["items"]), 1)
        self.assertEqual(client.get("/api/recommendations?limit=0").status_code, 400)
        self.assertEqual(client.get("/api/recommendations?limit=51").status_code, 400)

    def test_explicit_style_preference_beats_featured_fallback(self):
        style = Tag(name="印象派", category="style")
        db.session.add(style)
        matching = self.artwork("偏好作品", tags=[style])
        self.artwork("其他精选", featured=True)
        viewer = self.user("viewer")
        viewer.preferences = [style]
        db.session.commit()
        data = self.client(viewer).get("/api/recommendations?kind=personal").json
        self.assertEqual(data["strategy"], "preferences")
        self.assertEqual(data["items"][0]["id"], matching.id)
        self.assertEqual(data["items"][0]["recommendation_reason"], "符合你偏好的风格")

    def test_views_influence_style_and_seen_works_move_to_end(self):
        style = Tag(name="水彩", category="style")
        db.session.add(style)
        seen = self.artwork("已浏览", tags=[style])
        similar = self.artwork("同风格", tags=[style])
        self.artwork("其他风格")
        viewer = self.user("viewer")
        db.session.add(BehaviorLog(user_id=viewer.id, artwork_id=seen.id, action="view"))
        db.session.commit()
        data = self.client(viewer).get("/api/recommendations?kind=personal").json
        self.assertEqual(data["strategy"], "hybrid")
        self.assertEqual(data["items"][0]["id"], similar.id)
        self.assertEqual(data["items"][0]["recommendation_reason"], "与浏览历史风格相近")
        self.assertEqual(data["items"][-1]["id"], seen.id)

    def test_itemcf_uses_active_favorites_not_old_action_logs(self):
        source = self.artwork("共同收藏")
        collaborative = self.artwork("协同候选")
        featured = self.artwork("精选", featured=True)
        peer = self.user("peer")
        viewer = self.user("viewer")
        db.session.add_all([
            Favorite(user_id=peer.id, artwork_id=source.id),
            Favorite(user_id=peer.id, artwork_id=collaborative.id),
            Favorite(user_id=viewer.id, artwork_id=source.id),
            RecommendationSetting(key="itemcf_weight", value="10"),
        ])
        db.session.commit()
        client = self.client(viewer)
        first = client.get("/api/recommendations?kind=personal").json["items"]
        self.assertEqual(first[0]["id"], collaborative.id)
        self.assertEqual(first[0]["recommendation_reason"], "欣赏相近作品的用户也喜欢")

        db.session.delete(db.session.get(Favorite, (peer.id, collaborative.id)))
        db.session.add(BehaviorLog(user_id=peer.id, artwork_id=collaborative.id, action="favorite"))
        db.session.commit()
        self.assertEqual(client.get("/api/recommendations?kind=personal").json["items"][0]["id"], featured.id)

    def test_personal_excludes_disliked_work_even_at_cold_start(self):
        disliked = self.artwork("不喜欢", featured=True)
        acceptable = self.artwork("可推荐")
        self.artwork("已下架", status="archived")
        viewer = self.user("viewer")
        db.session.add_all([
            Rating(user_id=viewer.id, artwork_id=disliked.id, score=1),
            BehaviorLog(user_id=viewer.id, artwork_id=disliked.id, action="view"),
        ])
        db.session.commit()
        data = self.client(viewer).get("/api/recommendations?kind=personal").json
        self.assertEqual(data["strategy"], "cold_start")
        self.assertEqual([item["id"] for item in data["items"]], [acceptable.id])


if __name__ == "__main__":
    unittest.main()
