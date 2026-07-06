from flask import Blueprint, render_template

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    # Phase 1: 정적 이식. 실데이터 연동은 Phase 5(/api/home 서비스 함수)
    return render_template("main/index.html", active_menu="home")
