import time

from flask import Flask, g, session
from flask_compress import Compress

from config import Config
from extensions import cache, db

# 정적 자산 캐시버스팅 버전 — 서버 재시작(배포)마다 갱신되어
# 30일 Cache-Control에도 브라우저가 새 CSS/JS를 즉시 받는다
ASSET_VERSION = int(time.time())


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    @app.url_defaults
    def _static_cache_bust(endpoint, values):
        if endpoint == "static":
            values.setdefault("v", ASSET_VERSION)

    db.init_app(app)
    cache.init_app(app)
    Compress(app)  # 응답 gzip (§2-1)

    import models  # noqa: F401 — create_all 등록 보장

    from routes import register_blueprints

    register_blueprints(app)

    @app.before_request
    def load_current_user():
        g.user = None
        user_id = session.get("user_id")
        if user_id:
            from models import User

            user = db.session.get(User, user_id)
            if user is None or user.status in ("suspended", "withdrawn"):
                session.clear()
            else:
                g.user = user

    @app.context_processor
    def inject_globals():
        return {
            "current_user": g.get("user"),
            "site_name": app.config["SITE_NAME"],
            "site_name_en": app.config["SITE_NAME_EN"],
        }

    @app.cli.command("seed")
    def seed_command():
        """DB 생성 + 17테이블 + 시드 데이터."""
        from seed import run_seed

        run_seed(app)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
