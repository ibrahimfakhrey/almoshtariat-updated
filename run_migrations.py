from flask_app import app
from alembic.config import Config
from alembic import command

with app.app_context():
    alembic_cfg = Config("migrations/alembic.ini")
    command.upgrade(alembic_cfg, "head")