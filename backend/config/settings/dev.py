from .base import *

DEBUG = True
# runserver serves static files itself; WhiteNoise is only needed in production.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]  # noqa: F405
