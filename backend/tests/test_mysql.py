"""Optional MySQL integration check using a disposable, uniquely named database."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pymysql
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import URL
from sqlalchemy.schema import CreateIndex, CreateTable

from app import create_app
from app.extensions import db
from app.models import BehaviorLog, Favorite, User


class MySQLSchemaCompileTest(unittest.TestCase):
    def test_all_tables_compile_for_mysql(self):
        app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
        with app.app_context():
            tables = db.metadata.sorted_tables
            self.assertGreaterEqual(len(tables), 10)
            for table in tables:
                self.assertIn("CREATE TABLE", str(CreateTable(table).compile(dialect=mysql.dialect())))
                for index in table.indexes:
                    self.assertIn("INDEX", str(CreateIndex(index).compile(dialect=mysql.dialect())))


@unittest.skipUnless(os.getenv("MYSQL_TEST_PASSWORD"), "MYSQL_TEST_PASSWORD is not set")
class MySQLIntegrationTest(unittest.TestCase):
    def test_mysql_schema_and_api_flow(self):
        host = os.getenv("MYSQL_TEST_HOST", "127.0.0.1")
        user = os.getenv("MYSQL_TEST_USER", "root")
        password = os.environ["MYSQL_TEST_PASSWORD"]
        database = f"tk_smoke_{uuid4().hex[:12]}"
        connection = pymysql.connect(host=host, user=user, password=password, autocommit=True)
        created = False
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
            created = True
            uri = URL.create(
                "mysql+pymysql", username=user, password=password,
                host=host, database=database, query={"charset": "utf8mb4"},
            )
            app = create_app({"TESTING": True, "SECRET_KEY": "mysql-test", "SQLALCHEMY_DATABASE_URI": uri})
            with app.app_context():
                db.create_all()
                admin = User(username="admin", display_name="Admin", role="admin")
                admin.set_password("admin-password")
                db.session.add(admin)
                db.session.commit()
                administrator = app.test_client()
                visitor = app.test_client()
                self.assertEqual(administrator.post("/api/auth/login", json={"username": "admin", "password": "admin-password"}).status_code, 200)
                tag_id = administrator.post("/api/admin/tags", json={"name": "国风", "category": "style"}).json["item"]["id"]
                artwork = administrator.post("/api/admin/artworks", json={"title": "示例", "image_url": "https://example.test/art.jpg", "status": "published", "tag_ids": [tag_id]})
                self.assertEqual(artwork.status_code, 201)
                registered = visitor.post("/api/auth/register", json={"username": "visitor", "password": "visitor-password"})
                self.assertEqual(registered.status_code, 201)
                self.assertEqual(visitor.get("/api/artworks", query_string={"style": tag_id}).json["total"], 1)
                self.assertEqual(visitor.get("/api/recommendations?kind=personal").status_code, 200)
                artwork_id = artwork.json["item"]["id"]
                user_id = registered.json["user"]["id"]
                with visitor.session_transaction() as session:
                    authenticated_session = dict(session)
                for active in (True, False):
                    barrier = Barrier(10)

                    def change_favorite(_):
                        client = app.test_client()
                        with client.session_transaction() as session:
                            session.update(authenticated_session)
                        barrier.wait(timeout=10)
                        response = client.put(f"/api/artworks/{artwork_id}/interaction", json={"action": "favorite", "active": active})
                        return response.status_code, response.json.get("favorited")

                    with ThreadPoolExecutor(max_workers=10) as pool:
                        responses = list(pool.map(change_favorite, range(10)))
                    self.assertEqual(responses, [(200, active)] * 10)
                # The main test session must leave its earlier repeatable-read snapshot.
                db.session.rollback()
                self.assertIsNone(db.session.get(Favorite, (user_id, artwork_id)))
                actions = db.session.scalars(db.select(BehaviorLog.action).where(BehaviorLog.user_id == user_id)).all()
                self.assertEqual(sorted(actions), ["favorite", "unfavorite"])
                db.session.remove()
                db.engine.dispose()
        finally:
            if created:
                with connection.cursor() as cursor:
                    cursor.execute(f"DROP DATABASE `{database}`")
            connection.close()
