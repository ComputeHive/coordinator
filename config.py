import os
from dotenv import load_dotenv
load_dotenv()

class BaseConfig:
    SERVER_PATH = "http://127.0.0.1:5000/"
    MAIL_SERVER = "smtp.zoho.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    CODE_KEY = "ceraCode"
    MAIL_USERNAME = "no-reply@cera.tech"
    MAIL_PASSWORD = ""
    FRONT_END_ROOT = "http://www.cera.tech"

    # Read as string; app.py converts to bytes for Fernet
    SECRET_KEY: str = os.environ["SECRET_KEY"]
    SHARD_ID_KEY: str = os.environ["SHARD_ID_KEY"]


class DevelopmentConfig(BaseConfig):
    ENV = "development"
    DEBUG = True
    DATABASE_URI: str = os.environ["MONGODB_DEV_URI"]
    DATABASE_NAME: str = os.environ["MONGODB_DEV_NAME"]


class ProductionConfig(BaseConfig):
    ENV = "production"
    DEBUG = False
    DATABASE_URI: str = os.environ["MONGODB_PROD_URI"]
    DATABASE_NAME: str = os.environ["MONGODB_PROD_NAME"]
