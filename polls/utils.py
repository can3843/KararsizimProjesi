import secrets
import string

_PUBLIC_ID_ALPHABET = string.ascii_letters + string.digits


def generate_public_id(length=11):
    return "".join(secrets.choice(_PUBLIC_ID_ALPHABET) for _ in range(length))
