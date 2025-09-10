from flask import Flask, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config
from flask_migrate import Migrate
from flask_babel import Babel, gettext, ngettext
from flask_wtf.csrf import CSRFProtect

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Configure Babel
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)

# Initialize Flask-Babel (required for Flask-Admin)
from flask_babel import Babel

def get_locale():
    # First check if language is set in cookies (from JavaScript toggle)
    if 'language' in request.cookies:
        lang = request.cookies.get('language')
        print(f"DEBUG: Language from cookie: {lang}")
        return lang
    # Check if language is set in session (fallback)
    if 'language' in session:
        lang = session['language']
        print(f"DEBUG: Language from session: {lang}")
        return lang
    # Try to guess the language from the user accept
    # header the browser transmits. The best match wins.
    default_locale = request.accept_languages.best_match(['en', 'ar'])
    print(f"DEBUG: Default locale from browser: {default_locale}")
    return default_locale or 'en'

babel = Babel(app, locale_selector=get_locale)

# Make get_locale available to templates
@app.context_processor
def inject_get_locale():
    return dict(get_locale=get_locale)

# Add custom Jinja2 filter for JSON parsing
@app.template_filter('from_json')
def from_json_filter(json_str):
    import json
    try:
        return json.loads(json_str) if json_str else []
    except (json.JSONDecodeError, TypeError):
        return []

# Make common functions available to templates
@app.context_processor
def inject_template_functions():
    return dict(
        min=min,
        max=max,
        len=len,
        str=str,
        int=int
    )

# Add cache-busting headers to prevent browser caching
@app.after_request
def add_cache_headers(response):
    # Prevent caching of HTML pages
    if response.mimetype == 'text/html':
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Add version parameter to static files for cache busting
@app.context_processor
def inject_version():
    import time
    return dict(version=int(time.time()))

# Initialize admin views
from models import init_admin, register_admin_views
admin = init_admin(app)
register_admin_views(admin)