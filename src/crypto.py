import base64
import json
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

# Fixed salt matching Chrome extension's FIXED_SALT
FIXED_SALT = b"cookie-manager-salt-v1"

class Crypto:
    def __init__(self, master_password: str):
        self.master_password = master_password.encode()

    def derive_key(self, salt: bytes = None) -> bytes:
        """Derive AES key from master password using PBKDF2 (100,000 iterations)"""
        # Use fixed salt if not provided (to match Chrome extension)
        if salt is None:
            salt = FIXED_SALT
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(self.master_password)

    def decrypt(self, payload: dict) -> dict:
        """
        Decrypt E2EE payload
        payload = {
            "version": 1,
            "iv": "base64",       # Chrome extension format (no salt)
            "ciphertext": "base64"
        }
        or with salt (other formats):
        payload = {
            "version": 1,
            "salt": "base64",
            "iv": "base64",
            "ciphertext": "base64"
        }
        Returns decrypted JSON as dict
        """
        iv = base64.b64decode(payload["iv"])
        ciphertext = base64.b64decode(payload["ciphertext"])

        # Use salt from payload if present, otherwise use fixed salt
        if "salt" in payload:
            salt = base64.b64decode(payload["salt"])
        else:
            salt = FIXED_SALT

        key = self.derive_key(salt)
        aesgcm = AESGCM(key)

        plaintext = aesgcm.decrypt(iv, ciphertext, None)
        return json.loads(plaintext.decode())