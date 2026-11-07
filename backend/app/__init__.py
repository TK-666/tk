import os
from pathlib import Path

import click
from flask import Flask, jsonify
from flask.cli import with_appcontext
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException

from .config import Config
from .extensions import db


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    upload_path = Path(app.config["UPLOAD_FOLDER"])
    if not upload_path.is_absolute():
        upload_path = Path(app.instance_path) / upload_path
    app.config["UPLOAD_FOLDER"] = str(upload_path)
    upload_path.mkdir(parents=True, exist_ok=True)
    db.init_app(app)

    from . import models  # noqa: F401 - register all tables
    from .api import api

    app.register_blueprint(api, url_prefix="/api")

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        db.session.rollback()
        return jsonify(error="数据冲突，请检查重复项或关联记录"), 409

    @app.cli.command("init-db")
    @with_appcontext
    def init_db():
        """Create tables for local development; use migrations for deployed databases."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("create-admin")
    @click.argument("username")
    @with_appcontext
    def create_admin(username):
        """Create an administrator using ADMIN_PASSWORD from the environment."""
        from .models import User

        password = os.getenv("ADMIN_PASSWORD")
        if not password or len(password) < 8:
            raise click.UsageError("Set ADMIN_PASSWORD to at least 8 characters")
        if db.session.scalar(db.select(User).filter_by(username=username)):
            raise click.UsageError("Username already exists")
        user = User(username=username, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Administrator {username} created.")

    return app
