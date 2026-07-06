from flask import Blueprint, render_template

bp = Blueprint("counsel", __name__, url_prefix="/counsel")


@bp.route("/")
def list_():
    return render_template(
        "_placeholder.html", active_menu="counsel", page_title="상담사례", phase=4
    )
