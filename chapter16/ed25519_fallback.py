"""A small pure-Python Ed25519 (RFC 8032), used only when `cryptography` is absent.

It exposes the few names mandate.py needs, with the same behaviour as the
`cryptography` package: Ed25519PrivateKey.from_private_bytes / generate / sign /
public_key, Ed25519PublicKey.from_public_bytes / verify / public_bytes_raw, and
InvalidSignature. It follows the RFC's reference algorithm; it is slower than
the real library (a few milliseconds per verification) and is not hardened
against timing attacks, so use `pip install cryptography` for anything real.
"""
import hashlib
import os
from functools import lru_cache

p = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
d = -121665 * pow(121666, p - 2, p) % p
SQRT_M1 = pow(2, (p - 1) // 4, p)


class InvalidSignature(Exception):
    pass


def _add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % p
    C = 2 * P[3] * Q[3] * d % p
    D = 2 * P[2] * Q[2] % p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % p, G * H % p, F * G % p, E * H % p)


def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q):
    return (P[0] * Q[2] - Q[0] * P[2]) % p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % p == 0


def _recover_x(y, sign):
    if y >= p:
        return None
    x2 = (y * y - 1) * pow(d * y * y + 1, p - 2, p) % p
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p:
        x = x * SQRT_M1 % p
    if (x * x - x2) % p:
        return None
    if (x & 1) != sign:
        x = p - x
    return x


_GY = 4 * pow(5, p - 2, p) % p
_GX = _recover_x(_GY, 0)
G = (_GX, _GY, 1, _GX * _GY % p)


def _compress(P):
    zinv = pow(P[2], p - 2, p)
    x, y = P[0] * zinv % p, P[1] * zinv % p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % p)


def _h(m):
    return int.from_bytes(hashlib.sha512(m).digest(), "little") % L


@lru_cache(maxsize=65536)
def _verify(public, signature, data):
    A = _decompress(public)
    R = _decompress(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if A is None or R is None or s >= L:
        return False
    k = _h(signature[:32] + public + data)
    return _equal(_mul(s, G), _add(R, _mul(k, A)))


class Ed25519PublicKey:
    def __init__(self, raw: bytes):
        self._raw = bytes(raw)

    @classmethod
    def from_public_bytes(cls, data: bytes):
        return cls(data)

    def public_bytes_raw(self) -> bytes:
        return self._raw

    def verify(self, signature: bytes, data: bytes) -> None:
        if len(signature) != 64 or not _verify(self._raw, bytes(signature), bytes(data)):
            raise InvalidSignature()


class Ed25519PrivateKey:
    def __init__(self, seed: bytes):
        self._seed = bytes(seed)
        h = hashlib.sha512(self._seed).digest()
        a = int.from_bytes(h[:32], "little")
        a &= (1 << 254) - 8
        a |= 1 << 254
        self._a, self._prefix = a, h[32:]
        self._public = _compress(_mul(a, G))

    @classmethod
    def generate(cls):
        return cls(os.urandom(32))

    @classmethod
    def from_private_bytes(cls, data: bytes):
        if len(data) != 32:
            raise ValueError("An Ed25519 private key is 32 bytes long")
        return cls(data)

    def public_key(self) -> Ed25519PublicKey:
        return Ed25519PublicKey(self._public)

    def sign(self, data: bytes) -> bytes:
        r = _h(self._prefix + data)
        Rs = _compress(_mul(r, G))
        s = (r + _h(Rs + self._public + data) * self._a) % L
        return Rs + int.to_bytes(s, 32, "little")
