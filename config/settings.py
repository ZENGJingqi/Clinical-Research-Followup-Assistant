"""
Django settings for config project.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


for env_file_name in (".env.local", ".env.server"):
    _load_env_file(BASE_DIR / env_file_name)


def _split_env_list(name):
    raw_value = os.environ.get(name, "")
    return [item.strip() for item in raw_value.split(",") if item.strip()]

SECRET_KEY = os.environ.get(
    "FOLLOWUP_SECRET_KEY",
    "django-insecure-mxeuzsp&sol&18l*iqs%)h!$^fb6_@6i=ifo&798ye+m7(cw+v",
)
DEBUG = os.environ.get("FOLLOWUP_DEBUG", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
DEFAULT_ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
ALLOWED_HOSTS = _split_env_list("FOLLOWUP_ALLOWED_HOSTS") or DEFAULT_ALLOWED_HOSTS
CSRF_TRUSTED_ORIGINS = _split_env_list("FOLLOWUP_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'followup',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'followup.context_processors.app_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DEFAULT_DB_PATH = BASE_DIR / "data" / "db.sqlite3"
DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('FOLLOWUP_DB_PATH', str(DEFAULT_DB_PATH)),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

APP_NAME = '临床科研智能随访助手'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
AI_PROVIDER = os.environ.get("AI_PROVIDER", "aliyun").strip().lower() or "aliyun"
AI_API_KEY = os.environ.get("AI_API_KEY") or os.environ.get("ZAI_API_KEY", "")
AI_MODEL = os.environ.get(
    "AI_MODEL",
    "qwen-plus" if AI_PROVIDER == "aliyun" else "glm-5",
)
AI_BASE_URL = os.environ.get(
    "AI_BASE_URL",
    (
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        if AI_PROVIDER == "aliyun"
        else "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    ),
)
AI_USE_ENV_PROXY = os.environ.get("AI_USE_ENV_PROXY", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
AI_PROVIDER_MODEL_CHOICES = {
    "aliyun": [
        "qwen-turbo",
        "qwen-flash",
        "qwen-plus",
        "qwen-max",
    ],
    "zhipu": [
        "glm-4-flash",
        "glm-4-air",
        "glm-4-plus",
        "glm-5",
    ],
}
AI_TEXT_MODEL_CHOICES = AI_PROVIDER_MODEL_CHOICES.get(AI_PROVIDER, [AI_MODEL])
if AI_MODEL not in AI_TEXT_MODEL_CHOICES:
    AI_TEXT_MODEL_CHOICES = [AI_MODEL, *AI_TEXT_MODEL_CHOICES]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
