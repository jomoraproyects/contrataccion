import os
from pathlib import Path

import dj_database_url
from django.utils.csp import CSP
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

def env_bool(nombre, defecto=False):
    return os.environ.get(nombre, str(defecto)).strip().lower() in {"1", "true", "yes", "si"}


SECRET_KEY = os.environ.get("SECRET_KEY", "solo-desarrollo-cambiar-en-produccion")
DEBUG = env_bool("DEBUG", True)
if not DEBUG and (
    SECRET_KEY == "solo-desarrollo-cambiar-en-produccion"
    or SECRET_KEY.startswith("GENERE_")
    or len(SECRET_KEY) < 50
):
    raise ImproperlyConfigured("Debe configurar una SECRET_KEY aleatoria de al menos 50 caracteres.")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [u.strip() for u in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if u.strip()]
DATABASE_URL = os.environ.get("DATABASE_URL")
TRUST_PROXY_HEADERS = env_bool("TRUST_PROXY_HEADERS", False)
if not DEBUG and not DATABASE_URL:
    raise ImproperlyConfigured("Debe configurar DATABASE_URL con MySQL en producción.")
if not DEBUG and set(ALLOWED_HOSTS) <= {"localhost", "127.0.0.1"}:
    raise ImproperlyConfigured("Debe configurar ALLOWED_HOSTS con el dominio de producción.")
if not DEBUG and "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS no puede utilizar comodines en producción.")
if not DEBUG and (not CSRF_TRUSTED_ORIGINS or any(not origen.startswith("https://") for origen in CSRF_TRUSTED_ORIGINS)):
    raise ImproperlyConfigured("Debe configurar CSRF_TRUSTED_ORIGINS únicamente con orígenes HTTPS.")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "procesos.apps.ProcesosConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "procesos.middleware.AccesoPorRolMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "procesos.middleware.RespuestaSeguraMiddleware",
]

ROOT_URLCONF = "seleccion_personal.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "procesos.context_processors.user_role",
    ]},
}]
WSGI_APPLICATION = "seleccion_personal.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=DATABASE_URL or f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "600")),
        conn_health_checks=True,
    )
}
if not DEBUG and DATABASES["default"]["ENGINE"] != "django.db.backends.mysql":
    raise ImproperlyConfigured("Producción requiere una DATABASE_URL de MySQL.")
if DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
    DATABASES["default"].setdefault("OPTIONS", {}).update({
        "charset": "utf8mb4",
        "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        "connect_timeout": 5,
        "isolation_level": "read committed",
    })

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "procesos:lista"
LOGOUT_REDIRECT_URL = "login"

# Solo se confían cabeceras del proxy cuando Gunicorn está aislado detrás de Nginx.
# Esto evita que un cliente directo pueda falsificar X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if TRUST_PROXY_HEADERS else None
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600")) if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False) and not DEBUG
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False) and not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_NAME = "seleccion_session" if DEBUG else "__Host-seleccion_session"
SESSION_COOKIE_AGE = 4 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = False
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_NAME = "csrftoken" if DEBUG else "__Host-seleccion_csrf"
DATA_UPLOAD_MAX_MEMORY_SIZE = 1_048_576
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100

SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:"],
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "object-src": [CSP.NONE],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "produccion": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "produccion"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "procesos": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
