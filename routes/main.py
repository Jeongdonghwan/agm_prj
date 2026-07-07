import os
from datetime import datetime

from flask import Blueprint, abort, current_app, render_template, send_from_directory

from extensions import db
from models import Banner

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    # 히어로 배너: 배너 관리 연동 (기간 유효 + active, sort_order 우선)
    now = datetime.now()
    hero_banner = (
        Banner.query.filter(
            Banner.position == "main_hero",
            Banner.is_active.is_(True),
            db.or_(Banner.starts_at.is_(None), Banner.starts_at <= now),
            db.or_(Banner.ends_at.is_(None), Banner.ends_at >= now),
        )
        .order_by(Banner.sort_order)
        .first()
    )
    # 나머지 섹션 실데이터 연동은 Phase 5(/api/home 서비스 함수)
    return render_template(
        "main/index.html", active_menu="home", hero_banner=hero_banner
    )


@bp.route("/uploads/<path:filename>")
def uploads(filename):
    """공개 업로드 파일 서빙 (프로필 사진 등).

    인증 서류(verification/)는 admin 전용 라우트로만 — 여기서 차단 (§11).
    배포 시 nginx가 /uploads를 직접 서빙하되 /uploads/verification은 deny 설정 필요.
    """
    normalized = filename.replace("\\", "/")
    if normalized.startswith("verification/"):
        abort(403)
    return send_from_directory(
        os.path.normpath(current_app.config["UPLOAD_FOLDER"]), filename
    )
