import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parent.parent
PROBE = (
    "import json; from config import settings as s; "
    "print(json.dumps({k: getattr(s, k, None) for k in "
    "['SECURE_DEPLOYMENT', 'SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', "
    "'CSRF_COOKIE_SECURE', 'SECURE_PROXY_SSL_HEADER']}))"
)


def load_settings(**env):
    # Her denemede settings yeniden içe aktarılsın diye ayrı süreçte çalışır.
    base = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "VERCEL"))}
    base.update(DJANGO_SECRET_KEY="test-secret", VOTER_KEY_SALT="test-salt", **env)
    return subprocess.run(
        [sys.executable, "-c", PROBE], cwd=BASE_DIR, env=base, capture_output=True, text=True
    )


class ProductionSecuritySettingsTests(SimpleTestCase):
    def test_vercel_enables_https_settings(self):
        result = load_settings(VERCEL="1", DJANGO_DEBUG="False")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["SECURE_SSL_REDIRECT"])
        self.assertTrue(data["SESSION_COOKIE_SECURE"])
        self.assertTrue(data["CSRF_COOKIE_SECURE"])
        self.assertEqual(data["SECURE_PROXY_SSL_HEADER"], ["HTTP_X_FORWARDED_PROTO", "https"])

    def test_local_debug_false_keeps_http_working(self):
        result = load_settings(DJANGO_DEBUG="False")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data["SECURE_DEPLOYMENT"])
        self.assertFalse(data["SESSION_COOKIE_SECURE"])

    def test_explicit_flag_overrides_vercel_default(self):
        result = load_settings(VERCEL="1", DJANGO_SECURE="False", DJANGO_DEBUG="False")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["SECURE_DEPLOYMENT"])

    def test_secure_with_debug_is_rejected(self):
        result = load_settings(VERCEL="1", DJANGO_DEBUG="True")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_DEBUG", result.stderr)

    def test_missing_secret_key_fails_in_production(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "VERCEL"))}
        result = subprocess.run(
            [sys.executable, "-c", PROBE],
            cwd=BASE_DIR,
            env={**env, "VERCEL": "1", "DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": ""},
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_missing_voter_key_salt_fails_in_production(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "VERCEL", "VOTER_KEY_SALT"))}
        result = subprocess.run(
            [sys.executable, "-c", PROBE],
            cwd=BASE_DIR,
            env={**env, "DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": "test-secret", "VOTER_KEY_SALT": ""},
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VOTER_KEY_SALT", result.stderr)
