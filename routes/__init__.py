def register_blueprints(app):
    from routes.admin import bp as admin_bp
    from routes.api import bp as api_bp
    from routes.auth import bp as auth_bp
    from routes.community import bp as community_bp
    from routes.contents import bp as contents_bp
    from routes.counsel import bp as counsel_bp
    from routes.lawyer_admin import bp as lawyer_admin_bp
    from routes.lawyers import bp as lawyers_bp
    from routes.main import bp as main_bp
    from routes.mypage import bp as mypage_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(lawyers_bp)
    app.register_blueprint(counsel_bp)
    app.register_blueprint(contents_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(mypage_bp)
    app.register_blueprint(lawyer_admin_bp, url_prefix="/lawyer")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api")
