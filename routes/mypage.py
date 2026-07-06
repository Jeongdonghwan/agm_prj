from flask import Blueprint, render_template

from routes.decorators import login_required

bp = Blueprint("mypage", __name__, url_prefix="/mypage")


@bp.route("/")
@login_required
def home():
    return render_template(
        "_placeholder.html", active_menu=None, page_title="마이페이지", phase=5
    )
