from flask import Blueprint, render_template

bp = Blueprint("lawyers", __name__, url_prefix="/lawyers")


@bp.route("/")
def find():
    return render_template(
        "_placeholder.html", active_menu="lawyers", page_title="변호사 찾기", phase=2
    )
