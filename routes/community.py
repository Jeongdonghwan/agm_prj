from flask import Blueprint, render_template

bp = Blueprint("community", __name__, url_prefix="/community")


@bp.route("/")
def list_():
    return render_template(
        "_placeholder.html", active_menu="community", page_title="커뮤니티", phase=4
    )
