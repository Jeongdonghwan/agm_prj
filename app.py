import time

from flask import Flask, g, request, session
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

    from utils import body_text, render_body

    app.jinja_env.filters["render_body"] = render_body
    app.jinja_env.filters["body_text"] = body_text

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

    @app.after_request
    def no_store_for_private(resp):
        # 로그인 사용자·어드민/변호사/마이페이지 응답은 브라우저 캐시 금지 —
        # 뒤로가기/캐시로 이전 상태 화면이 보이는 혼동 방지 (static은 30일 캐시 유지)
        path = request.path
        # 주의: /lawyers(공개 목록)는 제외 — 변호사 어드민은 /lawyer prefix
        is_private_path = (
            path.startswith(("/admin", "/mypage"))
            or path == "/lawyer"
            or path.startswith("/lawyer/")
        )
        if not path.startswith("/static") and (g.get("user") is not None or is_private_path):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.context_processor
    def inject_globals():
        from routes.community import get_menu

        return {
            "current_user": g.get("user"),
            "site_name": app.config["SITE_NAME"],
            "site_name_en": app.config["SITE_NAME_EN"],
            "community_menu": get_menu(),  # GNB 커뮤니티 메가메뉴 (DB 관리)
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
