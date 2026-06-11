import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class AES:
    def __init__(self, key: bytes):

        if len(key) != 32:
            raise ValueError("AES key must be 32 bytes (AES-256).")
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: bytes) -> bytes:
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, data: bytes) -> bytes:
        nonce = data[:12]
        ciphertext_with_tag = data[12:]
        return self._aesgcm.decrypt(nonce, ciphertext_with_tag, None)
