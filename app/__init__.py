from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from dotenv import load_dotenv
from urllib.parse import quote_plus
import os

load_dotenv()

db = SQLAlchemy()

login_manager = LoginManager()


def _migrate_member_columns():
    """Add new member columns if they don't exist."""

    from sqlalchemy import text, inspect

    inspector = inspect(db.engine)

    if 'members' not in inspector.get_table_names():
        return

    existing = {col['name'] for col in inspector.get_columns('members')}

    new_cols = {
        'updated_by': 'INTEGER',
        'inactive_date': 'TIMESTAMP',
        'deleted_date': 'TIMESTAMP',
        'deleted_by': 'INTEGER',
    }

    with db.engine.begin() as conn:

        for col, col_type in new_cols.items():

            if col not in existing:

                try:

                    conn.execute(
                        text(
                            f'''
                            ALTER TABLE members
                            ADD COLUMN IF NOT EXISTS {col} {col_type}
                            '''
                        )
                    )

                except Exception as e:

                    print(f'Member migration error: {e}')


def _migrate_user_columns():
    """Add new user columns if they don't exist."""

    from sqlalchemy import text, inspect

    inspector = inspect(db.engine)

    if 'users' not in inspector.get_table_names():
        return

    existing = {col['name'] for col in inspector.get_columns('users')}

    new_cols = {
        'failed_login_attempts': 'INTEGER DEFAULT 0',
        'account_locked_until': 'TIMESTAMP',
    }

    with db.engine.begin() as conn:

        for col, col_type in new_cols.items():

            if col not in existing:

                try:

                    conn.execute(
                        text(
                            f'''
                            ALTER TABLE users
                            ADD COLUMN IF NOT EXISTS {col} {col_type}
                            '''
                        )
                    )

                except Exception as e:

                    print(f'User migration error: {e}')


def get_database_uri():

    # Render PostgreSQL

    database_url = os.environ.get('DATABASE_URL')

    if database_url:

        if database_url.startswith('postgres://'):

            database_url = database_url.replace(
                'postgres://',
                'postgresql://',
                1
            )

        return database_url

    # Local PostgreSQL

    user = os.environ.get('DB_USER', 'postgres')

    password = os.environ.get('DB_PASSWORD', '')

    host = os.environ.get('DB_HOST', 'localhost')

    port = os.environ.get('DB_PORT', '5432')

    name = os.environ.get('DB_NAME', 'heartfulness')

    encoded_password = quote_plus(password)

    return (
        f'postgresql://{user}:{encoded_password}@{host}:{port}/{name}'
    )


def create_app():

    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static'
    )

    app.config['SECRET_KEY'] = os.environ.get(
        'SECRET_KEY',
        'heartfulness-ngo-secret-key-2024'
    )

    app.config['SQLALCHEMY_DATABASE_URI'] = get_database_uri()

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['UPLOAD_FOLDER'] = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'instance',
        'uploads'
    )

    app.config['BACKUP_FOLDER'] = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'instance',
        'backups'
    )

    os.makedirs(
        app.config['UPLOAD_FOLDER'],
        exist_ok=True
    )

    os.makedirs(
        app.config['BACKUP_FOLDER'],
        exist_ok=True
    )

    db.init_app(app)

    login_manager.init_app(app)

    login_manager.login_view = 'auth.login'

    login_manager.login_message = (
        'Please log in to access this page.'
    )

    login_manager.login_message_category = 'warning'

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):

        return User.query.get(int(user_id))

    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.members import members_bp
    from app.routes.categories import categories_bp
    from app.routes.sessions import sessions_bp
    from app.routes.attendance import attendance_bp
    from app.routes.reports import reports_bp
    from app.routes.users import users_bp
    from app.routes.audit import audit_bp
    from app.routes.backup import backup_bp
    from app.routes.csv_import import csv_import_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(csv_import_bp)

    with app.app_context():

        try:

            # Create tables
            db.create_all()

            # Run migrations
            _migrate_user_columns()

            _migrate_member_columns()

            # Run again safely
            db.create_all()

            from app.utils.seed import seed_data

            seed_data()

        except Exception as e:

            print(f'Database initialization error: {e}')

    return app
