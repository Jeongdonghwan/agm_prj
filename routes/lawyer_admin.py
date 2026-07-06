from flask import Blueprint, g, render_template

from models import ConsultationAnswer, LawyerPost
from routes.decorators import role_required

bp = Blueprint("lawyer_admin", __name__)


@bp.route("/")
@role_required("lawyer")
def dashboard():
    profile = g.user.lawyer_profile
    stats = {
        "view_count": profile.view_count if profile else 0,
        "contact_click_count": profile.contact_click_count if profile else 0,
        "answer_count": ConsultationAnswer.query.filter_by(lawyer_id=g.user.id).count(),
        "published_posts": LawyerPost.query.filter_by(
            lawyer_id=g.user.id, status="published"
        ).count(),
    }
    return render_template("lawyer_admin/dashboard.html", stats=stats, profile=profile)
