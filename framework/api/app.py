from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from framework.config import Config, config_map
from framework.models.user import db
from framework.api.routes.auth import auth_bp
from framework.api.routes.chat import chat_bp
from framework.api.routes.models import models_bp
from framework.api.routes.docs import docs_bp
from framework.api.routes.data_files import data_files_bp
from framework.api.routes.county import county_bp
from framework.api.routes.report import report_bp

def create_app(config_name: str = 'default') -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_map[config_name])

    CORS(app)
    jwt = JWTManager(app)
    db.init_app(app)

    @jwt.unauthorized_loader
    def unauthorized_callback(callback):
        return {"status": "error", "message": "未登录或登录已过期"}, 401

    @jwt.invalid_token_loader
    def invalid_token_callback(callback):
        return {"status": "error", "message": "无效的登录凭证"}, 401

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return {"status": "error", "message": "登录已过期，请重新登录"}, 401

    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(chat_bp, url_prefix='/api/v1/chat')
    app.register_blueprint(models_bp, url_prefix='/api/v1/models')
    app.register_blueprint(docs_bp, url_prefix='/api/v1/docs')
    app.register_blueprint(data_files_bp, url_prefix='/api/v1/data_files')
    app.register_blueprint(county_bp, url_prefix='/api/v1/county')
    app.register_blueprint(report_bp, url_prefix='/api/v1/report')

    @app.route('/')
    def index():
        return {"status": "ok", "message": "Unified Framework API"}

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)