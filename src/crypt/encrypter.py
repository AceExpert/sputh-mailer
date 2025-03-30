import json
import ecies

from typing import Iterable, Any

from consts import private_key, symm, symm_rev


class Encrypter:

    def __init__(self):
        pass

    def encrypt_s1(self, data: 'str | bytes | Iterable[str | bytes | int]') -> str:
        raise NotImplementedError

    def decrypt_s1(self, data: 'str | bytes | Iterable[str | bytes | int]') -> str:
        raise NotImplementedError

    def decrypt_s2(self, data: str, key: 'bytes | bytearray') -> str:
        raise NotImplementedError

    def encrypt(self, data: 'str | bytes | Iterable[str | bytes | int]', key: 'bytes | bytearray') -> str:
        raise NotImplementedError

    def decrypt(self, data: 'str | bytes | Iterable[str | bytes | int]', key: 'bytes | bytearray') -> str:
        return self.decrypt_s2(self.decrypt_s1(data), key)
    
    def generate_keys(self):
        raise NotImplemented

class ECC(Encrypter):

    def __init__(self, s: dict[str, Any] = symm, s2: dict[str, Any] = symm_rev):
        self.symm = s
        self.symm_rev = s2

    def encrypt_s1(self, data: 'str | bytes | Iterable[str | bytes | int]') -> str:
        return "".join(symm[i]for i in data)

    def decrypt_s1(self, data: 'str | bytes | Iterable[str | bytes | int]') -> str:
        return "".join(symm_rev[i]for i in data)

    def decrypt_s2(self, data: str, key: 'bytes | bytearray') -> str:
        enc = bytearray(json.loads(data))
        return ecies.decrypt(bytes(key), data = bytes(enc)).decode()

    def encrypt(self, data: 'str | bytes | Iterable[str | bytes | int]', key: 'bytes | bytearray') -> str:
        enc = ecies.encrypt(key, data = data.encode() if isinstance(data, str) else bytes(data))
        return self.encrypt_s1(json.dumps([*enc]))

    def decrypt(self, data: 'str | bytes | Iterable[str | bytes | int]', key: 'bytes | bytearray' = private_key) -> str:
        return self.decrypt_s2(self.decrypt_s1(data), key)
    
    def generate_keys(self):
        k = ecies.generate_key()
        return k.secret, k.public_key.format()