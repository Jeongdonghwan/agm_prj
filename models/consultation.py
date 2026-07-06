from sqlalchemy import func
from sqlalchemy.dialects.mysql import ENUM

from extensions import db


class Consultation(db.Model):
    __tablename__ = "consultations"
    __table_args__ = (
        db.Index("idx_cat", "category_id"),
        db.Index("idx_recent", db.text("created_at DESC")),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    title = db.Column(db.String(200))
    content = db.Column(db.Text)
    is_public = db.Column(db.Boolean, default=True)
    views = db.Column(db.Integer, default=0)
    status = db.Column(ENUM("open", "hidden", "deleted"), default="open")
    created_at = db.Column(db.DateTime, server_default=func.now())
    deleted_at = db.Column(db.DateTime)

    user = db.relationship("User")
    category = db.relationship("Category")
    answers = db.relationship("ConsultationAnswer", back_populates="consultation")


class ConsultationAnswer(db.Model):
    __tablename__ = "consultation_answers"
    __table_args__ = (
        db.UniqueConstraint("consultation_id", "lawyer_id", name="uq_one_answer"),
    )

    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(
        db.Integer, db.ForeignKey("consultations.id"), nullable=False
    )
    lawyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=func.now())
    deleted_at = db.Column(db.DateTime)

    consultation = db.relationship("Consultation", back_populates="answers")
    lawyer = db.relationship("User")
