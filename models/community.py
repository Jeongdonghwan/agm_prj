from sqlalchemy import func
from sqlalchemy.dialects.mysql import ENUM

from extensions import db

community_likes = db.Table(
    "community_likes",
    db.Column(
        "post_id", db.Integer, db.ForeignKey("community_posts.id"), primary_key=True
    ),
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
)


class CommunityPost(db.Model):
    __tablename__ = "community_posts"
    __table_args__ = (db.Index("idx_popular", db.text("likes DESC"), db.text("views DESC")),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category = db.Column(db.String(30))
    title = db.Column(db.String(200))
    content = db.Column(db.Text)
    is_anonymous = db.Column(db.Boolean, default=False)
    is_notice = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    likes = db.Column(db.Integer, default=0)
    status = db.Column(ENUM("open", "hidden", "deleted"), default="open")
    created_at = db.Column(db.DateTime, server_default=func.now())
    deleted_at = db.Column(db.DateTime)

    user = db.relationship("User")
    comments = db.relationship("CommunityComment", back_populates="post")


class CommunityComment(db.Model):
    __tablename__ = "community_comments"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(
        db.Integer, db.ForeignKey("community_posts.id"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("community_comments.id"))
    content = db.Column(db.Text)
    is_anonymous = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=func.now())
    deleted_at = db.Column(db.DateTime)

    post = db.relationship("CommunityPost", back_populates="comments")
    user = db.relationship("User")
    replies = db.relationship("CommunityComment", remote_side=[id])
