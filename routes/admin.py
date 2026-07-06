import os

from flask import Blueprint, abort, current_app, render_template, send_from_directory

from extensions import db
from models import (
    Consultation,
    LawyerPost,
    LawyerVerificationFile,
    Report,
    User,
)
from routes.decorators import role_required

bp = Blueprint("admin", __name__)


@bp.route("/")
@role_required("admin")
def dashboard():
    stats = {
        "total_users": User.query.filter_by(role="user").count(),
        "total_lawyers": User.query.filter_by(role="lawyer", status="active").count(),
        "today_consultations": Consultation.query.filter(
            db.func.date(Consultation.created_at) == db.func.curdate()
        ).count(),
        "pending_lawyers": User.query.filter_by(role="lawyer", status="pending").count(),
        "pending_posts": LawyerPost.query.filter_by(status="pending").count(),
        "new_reports": Report.query.filter_by(status="new").count(),
    }
    return render_template("admin/dashboard.html", stats=stats)


@bp.route("/verification-files/<int:file_id>")
@role_required("admin")
def verification_file(file_id):
    """인증 서류는 이 라우트로만 서빙 — 공개 URL 금지 (§11)."""
    vf = db.session.get(LawyerVerificationFile, file_id)
    if vf is None or not vf.file_url:
        abort(404)
    directory = os.path.normpath(current_app.config["UPLOAD_FOLDER"])
    return send_from_directory(directory, vf.file_url)
