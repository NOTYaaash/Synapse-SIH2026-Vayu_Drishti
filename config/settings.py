import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent

if os.name == 'nt':
    libs_dir = BASE_DIR / "gdal_bin" / "rasterio.libs"
    mod_spatialite_dir = BASE_DIR / "gdal_bin" / "mod_spatialite-5.1.0-win-amd64"
    if libs_dir.exists():
        
        gdal_dlls = list(libs_dir.glob("gdal*.dll"))
        geos_dlls = list(libs_dir.glob("geos_c*.dll"))
        mod_spatialite_path = mod_spatialite_dir / "mod_spatialite.dll"
        if gdal_dlls:
            GDAL_LIBRARY_PATH = str(gdal_dlls[0])
        if geos_dlls:
            GEOS_LIBRARY_PATH = str(geos_dlls[0])
        if mod_spatialite_path.exists():
            SPATIALITE_LIBRARY_PATH = str(mod_spatialite_path)
        os.environ["PATH"] = str(libs_dir) + os.pathsep + str(mod_spatialite_dir) + os.pathsep + os.environ.get("PATH", "")
        
        proj_db_path = mod_spatialite_dir / "proj.db"
        rasterio_proj_path = BASE_DIR / "gdal_bin" / "rasterio" / "proj_data" / "proj.db"
        if rasterio_proj_path.exists():
            os.environ["PROJ_LIB"] = str(rasterio_proj_path.parent)
            os.environ["PROJ_DATA"] = str(rasterio_proj_path.parent)
        elif proj_db_path.exists():
            os.environ["PROJ_LIB"] = str(mod_spatialite_dir)
            os.environ["PROJ_DATA"] = str(mod_spatialite_dir)

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key-sih2026")
DEBUG = os.getenv("DEBUG", "True") == "True"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "corsheaders",
    "rest_framework",
    "rest_framework_gis",
    "apps.cyclones",
    "apps.predictions",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "apps" / "predictions" / "templates",
            BASE_DIR / "frontend" / "dist",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if os.getenv("USE_SQLITE", "True") == "True":
  DATABASES = {
      "default": {
          "ENGINE": "django.contrib.gis.db.backends.spatialite",
          "NAME": BASE_DIR / "db.sqlite3",
      }
  }
else:
  DATABASES = {
      "default": {
          "ENGINE": "django.contrib.gis.db.backends.postgis",
          "NAME": os.getenv("DATABASE_NAME", "cyclone_db"),
          "USER": os.getenv("DATABASE_USER", "postgres"),
          "PASSWORD": os.getenv("DATABASE_PASSWORD", "postgres"),
          "HOST": os.getenv("DATABASE_HOST", "localhost"),
          "PORT": os.getenv("DATABASE_PORT", "5432"),
      }
  }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        )
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation.MinimumLengthValidator"
        )
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/assets/"
STATICFILES_DIRS = [BASE_DIR / "frontend" / "dist" / "assets"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CORS_ALLOW_CREDENTIALS = True

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND", "redis://localhost:6379/0"
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"