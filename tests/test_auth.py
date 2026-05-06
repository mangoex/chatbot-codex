import unittest

from app import auth


class AuthTests(unittest.TestCase):
    def test_hash_password_verifies_original_password(self):
        password_hash = auth.hash_password("correct horse battery staple")

        self.assertTrue(auth.verify_password("correct horse battery staple", password_hash))
        self.assertFalse(auth.verify_password("wrong password", password_hash))

    def test_verify_password_rejects_invalid_hashes(self):
        self.assertFalse(auth.verify_password("secret", None))
        self.assertFalse(auth.verify_password("secret", "not-a-valid-hash"))
        self.assertFalse(auth.verify_password("secret", "bcrypt$1$salt$digest"))


if __name__ == "__main__":
    unittest.main()
