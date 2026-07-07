import os

from flask import Blueprint, abort, current_app, render_template, send_from_directory

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    # Phase 1: 정적 이식. 실데이터 연동은 Phase 5(/api/home 서비스 함수)
    return render_template("main/index.html", active_menu="home")


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
