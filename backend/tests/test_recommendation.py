import unittest

from app import create_app
from app.extensions import db
from app.models import Artwork, BehaviorLog, Favorite, Rating, RecommendationSetting, Tag, User
from app.services.recommendation import _signals


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

    def user(self, name, role="user"):
        user = User(username=name, display_name=name, role=role)
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

    def recommendations(self, client, kind="personal"):
        response = client.get(f"/api/recommendations?kind={kind}")
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def order(self, client, kind="personal"):
        return [item["id"] for item in self.recommendations(client, kind)["items"]]

    def interact(self, client, artwork, action, **data):
        response = client.put(f"/api/artworks/{artwork.id}/interaction", json={"action": action, **data})
        self.assertEqual(response.status_code, 200, response.json)

    def test_views_likes_and_favorites_stack_cap_and_reverse(self):
        style = Tag(name="watercolor", category="style")
        other_style = Tag(name="oil", category="style")
        source = self.artwork("watercolor source", [style])
        match = self.artwork("watercolor candidate", [style])
        benchmark = self.artwork("oil source", [other_style])
        other_match = self.artwork("oil candidate", [other_style])
        viewer = self.user("viewer")
        db.session.commit()
        client, guest = self.client(viewer), self.client()
        latest = self.order(guest, "latest")
        self.interact(client, benchmark, "like", active=True)

        def check(interest, hot_score, first):
            profiles, popularity, _ = _signals()
            self.assertAlmostEqual(profiles[viewer.id].get(source.id, 0), interest)
            self.assertAlmostEqual(popularity[source.id], hot_score)
            self.assertEqual(self.order(client)[0], first.id)
            expected_hot = source if hot_score > 2 else benchmark
            self.assertEqual(self.order(guest, "hot")[0], expected_hot.id)
            self.assertEqual(self.order(guest), self.order(guest, "hot"))
            self.assertEqual(self.order(client, "latest"), latest)

        self.assertEqual(guest.get(f"/api/artworks/{source.id}").status_code, 200)
        check(0, 0, other_match)
        for count in (1, 2):
            self.assertEqual(client.get(f"/api/artworks/{source.id}").status_code, 200)
            check(0.2 * count, 0.25 * count, other_match)
        self.interact(client, source, "like", active=True)
        check(2.4, 2.5, match)
        self.interact(client, source, "favorite", active=True)
        check(5.4, 5.5, match)
        self.interact(client, source, "favorite", active=True)
        self.interact(client, source, "like", active=True)
        check(5.4, 5.5, match)
        self.interact(client, source, "favorite", active=False)
        check(2.4, 2.5, match)
        self.interact(client, source, "favorite", active=True)
        self.interact(client, source, "like", active=False)
        check(3.4, 3.5, match)
        self.interact(client, source, "favorite", active=False)
        check(0.4, 0.5, other_match)
        for _ in range(2):
            self.assertEqual(client.get(f"/api/artworks/{source.id}").status_code, 200)
            check(0.6, 0.75, other_match)

    def test_rating_replaces_previous_rating_and_low_rating_only_zeroes_that_users_signals(self):
        style = Tag(name="watercolor", category="style")
        other_style = Tag(name="oil", category="style")
        source = self.artwork("rated source", [style])
        match = self.artwork("watercolor candidate", [style])
        other_source = self.artwork("oil source", [other_style])
        other_match = self.artwork("oil candidate", [other_style])
        benchmark = self.artwork("popularity benchmark")
        viewer, peer = self.user("viewer"), self.user("peer")
        db.session.commit()
        client, other = self.client(viewer), self.client(peer)
        self.interact(other, source, "like", active=True)
        self.interact(other, benchmark, "favorite", active=True)
        self.assertEqual(client.get(f"/api/artworks/{other_source.id}").status_code, 200)
        self.interact(client, other_source, "rate", score=4)

        def check(interest, hot_score, excluded=False):
            profiles, popularity, disliked = _signals()
            self.assertAlmostEqual(profiles.get(viewer.id, {}).get(source.id, 0), interest)
            self.assertAlmostEqual(popularity[source.id], hot_score)
            self.assertEqual(source.id in disliked.get(viewer.id, set()), excluded)
            personal = self.order(client)
            self.assertEqual(source.id not in personal, excluded)
            self.assertEqual(personal.index(match.id) < personal.index(other_match.id), interest > 1.2)
            self.assertIn(source.id, self.order(other))
            hot = self.order(client, "hot")
            self.assertEqual(hot[0], source.id if hot_score > 3 else benchmark.id)
            self.assertIn(source.id, hot)
            self.assertIn(source.id, self.order(client, "latest"))

        for rating in (3, 4, 5):
            with self.subTest(rating=rating):
                self.interact(client, source, "rate", score=rating)
                check(rating - 3, 2 + rating - 3)
        for _ in range(2):
            self.assertEqual(client.get(f"/api/artworks/{source.id}").status_code, 200)
        self.interact(client, source, "like", active=True)
        self.interact(client, source, "favorite", active=True)
        self.interact(client, source, "rate", score=5)
        check(7.4, 9.5)
        for rating in (1, 2):
            with self.subTest(rating=rating):
                self.interact(client, source, "rate", score=rating)
                check(0, 2, excluded=True)
        self.interact(client, source, "rate", score=3)
        check(5.4, 7.5)

    def test_admin_weights_independently_change_personal_order_and_reason(self):
        style = Tag(name="watercolor", category="style")
        source = self.artwork("source", [style])
        tag_match = self.artwork("tag candidate", [style])
        cf_match = self.artwork("ItemCF candidate")
        viewer, peer, admin = self.user("viewer"), self.user("peer"), self.user("admin", role="admin")
        db.session.commit()
        client, other, manager = self.client(viewer), self.client(peer), self.client(admin)
        self.interact(client, source, "favorite", active=True)
        self.interact(other, source, "favorite", active=True)
        self.interact(other, cf_match, "favorite", active=True)
        guest = self.client()
        hot, latest = self.order(guest, "hot"), self.order(guest, "latest")
        tag_reason = "与浏览历史风格相近"
        cf_reason = "欣赏相近作品的用户也喜欢"

        def check(first, reason):
            personal = self.recommendations(client)
            self.assertEqual(personal["strategy"], "hybrid")
            self.assertEqual(personal["items"][0]["id"], first.id)
            self.assertEqual(personal["items"][0]["recommendation_reason"], reason)
            self.assertEqual(self.order(guest), hot)
            self.assertEqual(self.order(client, "hot"), hot)
            self.assertEqual(self.order(client, "latest"), latest)

        check(cf_match, cf_reason)
        self.assertEqual(client.put("/api/admin/settings", json={"tag_weight": 100}).status_code, 403)
        for changes, expected, first, reason in (
            ({"tag_weight": 100}, {"tag_weight": 100}, tag_match, tag_reason),
            ({"tag_weight": 0}, {"tag_weight": 0}, cf_match, cf_reason),
            ({"tag_weight": 3}, {"tag_weight": 3}, cf_match, cf_reason),
            ({"itemcf_weight": 0}, {"tag_weight": 3, "itemcf_weight": 0}, tag_match, tag_reason),
            ({"itemcf_weight": 100}, {"tag_weight": 3, "itemcf_weight": 100}, cf_match, cf_reason),
            ({"tag_weight": 0, "itemcf_weight": 0}, {"tag_weight": 0, "itemcf_weight": 0}, cf_match, "热门作品"),
            ({"tag_weight": 3, "itemcf_weight": 2}, {"tag_weight": 3, "itemcf_weight": 2}, cf_match, cf_reason),
        ):
            with self.subTest(changes=changes):
                response = manager.put("/api/admin/settings", json=changes)
                self.assertEqual(response.status_code, 200, response.json)
                saved = manager.get("/api/admin/settings").json["items"]
                self.assertEqual({key: float(value) for key, value in saved.items()}, expected)
                check(first, reason)
        for key in ("tag_weight", "itemcf_weight"):
            for value in (-1, 101, "invalid"):
                with self.subTest(key=key, value=value):
                    self.assertEqual(manager.put("/api/admin/settings", json={key: value}).status_code, 400)
        self.assertEqual(manager.get("/api/admin/settings").json["items"], {"tag_weight": "3.0", "itemcf_weight": "2.0"})

    def test_preferences_artwork_tags_and_admin_controls_change_ranking_inputs(self):
        style = Tag(name="watercolor", category="style")
        source = self.artwork("watercolor source", [style])
        match = self.artwork("watercolor candidate", [style])
        featured = self.artwork("editor pick")
        for artwork in (source, match, featured):
            artwork.image_url = "https://example.com/art.jpg"
        viewer, peer, admin = self.user("viewer"), self.user("peer"), self.user("admin", role="admin")
        db.session.commit()
        client, other, manager = self.client(viewer), self.client(peer), self.client(admin)
        self.interact(other, source, "favorite", active=True)

        def set_preferences(tag_ids):
            response = client.put("/api/auth/preferences", json={"tag_ids": tag_ids})
            self.assertEqual(response.status_code, 200, response.json)

        def update_artwork(artwork, **data):
            response = manager.patch(f"/api/admin/artworks/{artwork.id}", json=data)
            self.assertEqual(response.status_code, 200, response.json)

        update_artwork(featured, featured=True)
        self.assertEqual(self.order(client, "hot")[0], featured.id)
        self.assertEqual(self.recommendations(client)["strategy"], "cold_start")
        self.assertEqual(self.order(client)[0], featured.id)
        set_preferences([style.id])
        self.assertEqual(self.order(client), [source.id, match.id, featured.id])
        update_artwork(match, tag_ids=[])
        self.assertEqual(self.order(client), [source.id, featured.id, match.id])
        update_artwork(match, tag_ids=[style.id])
        self.assertEqual(self.order(client), [source.id, match.id, featured.id])
        set_preferences([])
        self.assertEqual(self.order(client)[0], featured.id)
        set_preferences([style.id])

        update_artwork(source, status="archived")
        for kind in ("personal", "hot", "latest"):
            self.assertNotIn(source.id, self.order(client, kind))
        update_artwork(source, status="published")
        self.assertEqual(self.order(client)[0], source.id)
        update_artwork(featured, featured=False)
        self.assertEqual(self.order(client, "hot")[0], source.id)

        response = manager.patch(f"/api/admin/users/{peer.id}", json={"enabled": False})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.order(client)[0], match.id)
        self.assertEqual(self.order(client, "hot")[0], featured.id)
        response = manager.patch(f"/api/admin/users/{peer.id}", json={"enabled": True})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.order(client)[0], source.id)
        self.assertEqual(self.order(client, "hot")[0], source.id)

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
