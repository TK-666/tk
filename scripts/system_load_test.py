"""Run a local HTTP load test with an isolated, disposable SQLite database.

Example: python scripts/system_load_test.py --requests 60 --output results.json
The server and clients run on the same machine; results are not production capacity.
"""

import argparse
import http.client
import json
import math
import os
import platform
import random
import shutil
import statistics
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from werkzeug.serving import WSGIRequestHandler, make_server


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Artwork, BehaviorLog, Favorite, Like, Rating, Tag, User  # noqa: E402


class QuietHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        pass


def make_fixture(temp_dir):
    manifest = json.loads((ROOT / "data" / "artworks.json").read_text(encoding="utf-8"))["artworks"]
    if len(manifest) != 46:
        raise ValueError("This benchmark expects the 46-artwork sample catalog")
    upload_dir = temp_dir / "uploads"
    upload_dir.mkdir()
    shutil.copyfile(ROOT / "data" / manifest[0]["image_file"], upload_dir / "sample.jpg")
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "isolated-load-test",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (temp_dir / "load.sqlite").as_posix(),
        "UPLOAD_FOLDER": str(upload_dir),
    })
    with app.app_context():
        db.create_all()
        tags = {}
        artworks = []
        for item in manifest:
            selected = []
            for entry in item["tags"]:
                key = (entry["category"], entry["name"])
                if key not in tags:
                    tags[key] = Tag(category=key[0], name=key[1])
                    db.session.add(tags[key])
                selected.append(tags[key])
            artwork = Artwork(title=item["title"], artist=(item.get("artist") or "")[:120],
                              image_url="/api/uploads/sample.jpg", status="published", tags=selected)
            artworks.append(artwork)
            db.session.add(artwork)
        user_template = User(username="load-00")
        user_template.set_password("load-test-password")
        users = [user_template] + [User(username=f"load-{index:02}", password_hash=user_template.password_hash)
                                  for index in range(1, 50)]
        db.session.add_all(users)
        db.session.flush()
        randomizer = random.Random(20261107)
        for user in users:
            chosen = randomizer.sample(artworks, 10)
            db.session.add_all(BehaviorLog(user_id=user.id, artwork_id=art.id, action="view") for art in chosen)
            db.session.add_all(Favorite(user_id=user.id, artwork_id=art.id) for art in chosen[:3])
            db.session.add_all(Like(user_id=user.id, artwork_id=art.id) for art in chosen[3:6])
            db.session.add(Rating(user_id=user.id, artwork_id=chosen[6].id, score=5))
        db.session.commit()
    with app.test_client() as client:
        result = client.post("/api/auth/login", json={"username": "load-00", "password": "load-test-password"})
        if result.status_code != 200:
            raise RuntimeError("Failed to authenticate the synthetic benchmark user")
        cookie = client.get_cookie("session")
        if cookie is None:
            raise RuntimeError("No benchmark session cookie")
        cookie_header = f"session={cookie.value}"
    return app, cookie_header


def request_once(port, path, cookie):
    started = time.perf_counter()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        headers = {"Cookie": cookie} if cookie else {}
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        if path.startswith("/api/uploads/"):
            if not response.getheader("Content-Type", "").startswith("image/") or len(body) < 1024:
                raise ValueError("Invalid image response")
        else:
            payload = json.loads(body)
            if not payload.get("items"):
                raise ValueError("Empty item list")
            if "kind=personal" in path and payload.get("strategy") != "hybrid":
                raise ValueError("Unexpected personal recommendation strategy")
        return (time.perf_counter() - started) * 1000, None
    except Exception as error:
        return (time.perf_counter() - started) * 1000, f"{type(error).__name__}: {error}"
    finally:
        connection.close()


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def run_stage(port, name, path, cookie, concurrency, count):
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda _: request_once(port, path, cookie), range(count)))
    duration = time.perf_counter() - started
    latencies = [latency for latency, error in results if error is None]
    errors = [error for _, error in results if error is not None]
    return {
        "endpoint": name, "path": path, "concurrency": concurrency,
        "requests": count, "successes": len(latencies), "errors": len(errors),
        "error_examples": sorted(set(errors))[:3], "duration_seconds": round(duration, 3),
        "requests_per_second": round(count / duration, 2),
        "median_ms": round(statistics.median(latencies), 2) if latencies else None,
        "p95_ms": round(percentile(latencies, 0.95), 2) if latencies else None,
        "p99_ms": round(percentile(latencies, 0.99), 2) if latencies else None,
    }


def set_favorite(port, cookie, active, barrier=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        if barrier:
            barrier.wait(timeout=10)
        body = json.dumps({"action": "favorite", "active": active})
        connection.request("PUT", "/api/artworks/1/interaction", body=body,
                           headers={"Cookie": cookie, "Content-Type": "application/json"})
        response = connection.getresponse()
        payload = json.loads(response.read())
        return response.status, payload.get("favorited")
    finally:
        connection.close()


def concurrent_favorite_check(app, port, cookie):
    status, value = set_favorite(port, cookie, False)
    if status != 200 or value is not False:
        raise RuntimeError("Could not prepare concurrent favorite test")
    with app.app_context():
        user_id = db.session.scalar(db.select(User.id).where(User.username == "load-00"))
        initial_removal_events = db.session.scalar(db.select(db.func.count()).select_from(BehaviorLog).where(
            BehaviorLog.user_id == user_id, BehaviorLog.artwork_id == 1, BehaviorLog.action == "unfavorite"))
    barrier = threading.Barrier(25)
    with ThreadPoolExecutor(max_workers=25) as pool:
        responses = list(pool.map(lambda _: set_favorite(port, cookie, True, barrier), range(25)))
    with app.app_context():
        favorites = db.session.scalar(db.select(db.func.count()).select_from(Favorite).where(
            Favorite.user_id == user_id, Favorite.artwork_id == 1))
        events = db.session.scalar(db.select(db.func.count()).select_from(BehaviorLog).where(
            BehaviorLog.user_id == user_id, BehaviorLog.artwork_id == 1, BehaviorLog.action == "favorite"))
    statuses = {}
    for status, _ in responses:
        statuses[str(status)] = statuses.get(str(status), 0) + 1
    barrier = threading.Barrier(25)
    with ThreadPoolExecutor(max_workers=25) as pool:
        removals = list(pool.map(lambda _: set_favorite(port, cookie, False, barrier), range(25)))
    with app.app_context():
        remaining = db.session.scalar(db.select(db.func.count()).select_from(Favorite).where(
            Favorite.user_id == user_id, Favorite.artwork_id == 1))
        removal_events = db.session.scalar(db.select(db.func.count()).select_from(BehaviorLog).where(
            BehaviorLog.user_id == user_id, BehaviorLog.artwork_id == 1, BehaviorLog.action == "unfavorite"))
    removal_statuses = {}
    for status, _ in removals:
        removal_statuses[str(status)] = removal_statuses.get(str(status), 0) + 1
    return {"requests": 25, "status_counts": statuses, "all_favorited": all(value is True for _, value in responses),
            "favorite_rows": favorites, "favorite_events": events, "removal_status_counts": removal_statuses,
            "all_removed": all(value is False for _, value in removals), "remaining_rows": remaining,
            "removal_events": removal_events - initial_removal_events}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=60, help="requests per endpoint and concurrency level")
    parser.add_argument("--output", type=Path, help="optional JSON results path")
    args = parser.parse_args()
    if args.requests < 25 or args.requests > 1000:
        parser.error("--requests must be between 25 and 1000")
    stages = [
        ("catalog", "/api/artworks?per_page=12", False),
        ("search", "/api/artworks?q=Monet", False),
        ("hot", "/api/recommendations?kind=hot", False),
        ("personal", "/api/recommendations?kind=personal", True),
        ("image", "/api/uploads/sample.jpg", False),
    ]
    with tempfile.TemporaryDirectory(prefix="art-system-load-") as directory:
        app, cookie = make_fixture(Path(directory))
        server = make_server("127.0.0.1", 0, app, threaded=True, request_handler=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for _, path, authenticated in stages:
                _, error = request_once(server.server_port, path, cookie if authenticated else None)
                if error:
                    raise RuntimeError(f"Warm-up failed for {path}: {error}")
            results = []
            for concurrency in (1, 10, 25):
                for name, path, authenticated in stages:
                    result = run_stage(server.server_port, name, path, cookie if authenticated else None, concurrency, args.requests)
                    results.append(result)
                    print(json.dumps(result, ensure_ascii=False), flush=True)
            write_check = concurrent_favorite_check(app, server.server_port, cookie)
            print(json.dumps({"concurrent_favorite": write_check}, ensure_ascii=False), flush=True)
            report = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "environment": {"os": platform.platform(), "python": platform.python_version(),
                                "flask": version("Flask"), "sqlalchemy": version("SQLAlchemy"),
                                "logical_cpus": os.cpu_count(), "database": "SQLite", "server": "Werkzeug threaded development server"},
                "fixture": {"artworks": 46, "synthetic_users": 50, "views": 500,
                            "favorites": 150, "likes": 150, "ratings": 50,
                            "client_and_server_same_machine": True},
                "results": results,
                "concurrent_favorite": write_check,
            }
            if args.output:
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if any(result["errors"] for result in results):
                raise SystemExit("One or more load-test requests failed")
            if (write_check["status_counts"] != {"200": 25} or not write_check["all_favorited"]
                    or write_check["favorite_rows"] != 1 or write_check["favorite_events"] != 1
                    or write_check["removal_status_counts"] != {"200": 25} or not write_check["all_removed"]
                    or write_check["remaining_rows"] != 0 or write_check["removal_events"] != 1):
                raise SystemExit("Concurrent favorite check failed")
        finally:
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()
            with app.app_context():
                db.session.remove()
                db.engine.dispose()


if __name__ == "__main__":
    main()
