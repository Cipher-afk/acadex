from passlib.context import CryptContext
from datetime import datetime, timedelta

context = CryptContext(["argon2"])


def hash_password(password):
    hashed_password = context.hash(password)
    return hashed_password


def verify_password(password, hashed_password):
    return True if context.verify(password, hashed_password) else False


