"""
Central blueprint registration.
Call register_blueprints(app) from the app factory.
"""
from flask import Flask


def register_blueprints(app: Flask) -> None:
    from web.routes.auth_routes import bp as auth_bp
    from web.routes.config_routes import bp as config_bp
    from web.routes.inference_routes import bp as inference_bp
    from web.routes.decision_tree_routes import bp as dt_bp
    from web.routes.file_manager_routes import bp as file_mgr_bp
    from web.routes.jira_routes import bp as jira_bp
    from web.routes.azure_routes import bp as azure_bp
    from web.routes.iteration_routes import bp as iteration_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(inference_bp)
    app.register_blueprint(dt_bp)
    app.register_blueprint(file_mgr_bp)
    app.register_blueprint(jira_bp)
    app.register_blueprint(azure_bp)
    app.register_blueprint(iteration_bp)
