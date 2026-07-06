from flask import Blueprint, render_template

bp = Blueprint("contents", __name__)


@bp.route("/posts")
def posts():
    return render_template(
        "_placeholder.html", active_menu="posts", page_title="변호사포스트", phase=3
    )


@bp.route("/cases")
def cases():
    return render_template(
        "_placeholder.html", active_menu="cases", page_title="판례돋보기", phase=3
    )


@bp.route("/news")
def news():
    return render_template(
        "_placeholder.html", active_menu="news", page_title="안기모뉴스", phase=3
    )


@bp.route("/firms")
def firms():
    return render_template(
        "_placeholder.html", active_menu="firms", page_title="로펌", phase=3
    )
