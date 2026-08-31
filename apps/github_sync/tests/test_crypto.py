from django.test import SimpleTestCase, override_settings

from apps.github_sync import crypto

from .conftest_settings import ENABLED_SETTINGS


@override_settings(**ENABLED_SETTINGS)
class CryptoTests(SimpleTestCase):
    def test_roundtrip(self):
        self.assertEqual(crypto.decrypt(crypto.encrypt("gho_secret")), "gho_secret")

    def test_ciphertext_is_not_plaintext(self):
        self.assertNotIn("gho_secret", crypto.encrypt("gho_secret"))


class CryptoWithoutKeyTests(SimpleTestCase):
    @override_settings(GITHUB_TOKEN_ENC_KEY=None)
    def test_missing_key_raises(self):
        with self.assertRaises(RuntimeError):
            crypto.encrypt("x")
