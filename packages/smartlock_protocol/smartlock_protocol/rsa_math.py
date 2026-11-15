"""RSA arithmetic for coursework, deliberately outside production transport.

This is variable-time, unpadded textbook RSA, with no blinding, authentication
or side-channel protection. Even a large modulus does not make this encryption
safe for real messages. Production code must use its existing vetted protocol.

Algorithms checked against the Handbook of Applied Cryptography: 2.107/2.142
(extended Euclid/inverse), 2.143 (square-and-multiply), 4.24/4.44 (Miller-Rabin
and probable-prime search), and 8.1/8.3 (RSA). These are fresh implementations
of the mathematical algorithms, not copied library code.
https://cacr.uwaterloo.ca/hac/about/chap2.pdf
https://cacr.uwaterloo.ca/hac/about/chap4.pdf
https://cacr.uwaterloo.ca/hac/about/chap8.pdf
RFC 8017 sections 5 and 7 distinguish RSA primitives from padded encryption:
https://www.rfc-editor.org/rfc/rfc8017.html
"""
from dataclasses import dataclass
import secrets


SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)
MAX_PRIME_BITS = 4096
DEFAULT_ROUNDS = 32


def _integer(value, name):
    if type(value) is not int:
        raise ValueError(f'{name} must be an integer, not bool or a coercible value')
    return value


def _rounds(value):
    _integer(value, 'rounds')
    if not 1 <= value <= 128:
        raise ValueError('Use 1..128 independent Miller-Rabin rounds')
    return value


def mod_exp(base, exponent, modulus):
    """Right-to-left square-and-multiply; O(log exponent) modular products.

    No built-in pow() is used. Negative bases are normalized, exponents must
    be nonnegative, and modulus 1 follows the ordinary modular convention.
    """
    for name, value in (('base', base), ('exponent', exponent), ('modulus', modulus)):
        _integer(value, name)
    if exponent < 0 or modulus < 1:
        raise ValueError('Require exponent >= 0 and modulus >= 1')
    result = 1 % modulus
    factor = base % modulus
    while exponent:
        if exponent & 1:
            result = result * factor % modulus
        exponent >>= 1
        if exponent:
            factor = factor * factor % modulus
    return result


def extended_gcd(a, b):
    """Return nonnegative gcd and Bezout coefficients: a*x + b*y == gcd."""
    _integer(a, 'a')
    _integer(b, 'b')
    previous, current = abs(a), abs(b)
    x0, x1, y0, y1 = 1, 0, 0, 1
    while current:
        quotient, remainder = divmod(previous, current)
        previous, current = current, remainder
        x0, x1 = x1, x0 - quotient * x1
        y0, y1 = y1, y0 - quotient * y1
    return previous, x0 if a >= 0 else -x0, y0 if b >= 0 else -y0


def mod_inverse(value, modulus):
    """Find a canonical inverse using extended Euclid, or reject non-coprimes."""
    _integer(value, 'value')
    _integer(modulus, 'modulus')
    if modulus < 2:
        raise ValueError('Inverse modulus must be >= 2')
    divisor, coefficient, _ = extended_gcd(value, modulus)
    if divisor != 1:
        raise ValueError('Inverse does not exist for non-coprime integers')
    return coefficient % modulus


def is_probable_prime(candidate, rounds=DEFAULT_ROUNDS):
    """Miller-Rabin with independent secrets.randbelow bases, after trial division.

    True means probable prime, not a proof. For a fixed odd composite, the
    false-positive bound is at most 4**(-rounds) with these uniformly sampled
    independent bases. This is not a posterior bound for a generated key.
    """
    _integer(candidate, 'candidate')
    _rounds(rounds)
    if candidate < 2:
        return False
    if candidate.bit_length() > MAX_PRIME_BITS:
        raise ValueError('Candidate exceeds the coursework size limit')
    for prime in SMALL_PRIMES:
        if candidate == prime:
            return True
        if candidate % prime == 0:
            return False
    odd_part, powers_of_two = candidate - 1, 0
    while odd_part % 2 == 0:
        odd_part //= 2
        powers_of_two += 1
    for _ in range(rounds):
        base = 2 + secrets.randbelow(candidate - 3)
        value = mod_exp(base, odd_part, candidate)
        if value in (1, candidate - 1):
            continue
        for _ in range(powers_of_two - 1):
            value = value * value % candidate
            if value == candidate - 1:
                break
            if value == 1:
                return False
        else:
            return False
    return True


def generate_prime(bits, rounds=DEFAULT_ROUNDS, *, max_attempts=100000):
    """Bounded random search for an exact-bit-length odd probable prime."""
    _integer(bits, 'bits')
    _rounds(rounds)
    _integer(max_attempts, 'max_attempts')
    if not 2 <= bits <= MAX_PRIME_BITS or not 1 <= max_attempts <= 100000:
        raise ValueError('Use 2..4096 bits and 1..100000 attempts')
    for _ in range(max_attempts):
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(candidate, rounds):
            return candidate
    raise RuntimeError('Probable-prime search exhausted its attempt budget')


@dataclass(frozen=True, repr=False)
class TeachingKeyPair:
    """Sensitive arithmetic parameters; never serialize this object into reports."""
    n: int
    e: int
    d: int
    p: int
    q: int

    def __repr__(self):
        return f'TeachingKeyPair(bits={self.n.bit_length()}, teaching_only=True)'


def key_from_primes(p, q, e=65537, *, rounds=DEFAULT_ROUNDS):
    """Construct textbook RSA using phi(n); also supports small worked examples."""
    for name, value in (('p', p), ('q', q), ('e', e)):
        _integer(value, name)
    _rounds(rounds)
    if p == q or p < 3 or q < 3 or p % 2 == 0 or q % 2 == 0:
        raise ValueError('Require distinct odd probable primes')
    if not is_probable_prime(p, rounds) or not is_probable_prime(q, rounds):
        raise ValueError('RSA factors must pass probable-prime checks')
    phi = (p - 1) * (q - 1)
    if not 3 <= e < phi or e % 2 == 0:
        raise ValueError('Public exponent must be odd and satisfy 3 <= e < phi(n)')
    return TeachingKeyPair(p * q, e, mod_inverse(e, phi), p, q)


def generate_keypair(bits=1024, e=65537, *, rounds=DEFAULT_ROUNDS):
    """Generate a 512..4096-bit coursework key; no production security claim."""
    _integer(bits, 'bits')
    _integer(e, 'e')
    _rounds(rounds)
    if not 512 <= bits <= 4096:
        raise ValueError('Use 512..4096 bits for generated coursework keys')
    if not 3 <= e < (1 << (bits - 2)) or e % 2 == 0:
        raise ValueError('Invalid public exponent')
    for _ in range(128):
        p = generate_prime(bits // 2, rounds)
        q = generate_prime(bits - bits // 2, rounds)
        if p == q or (p * q).bit_length() != bits:
            continue
        phi = (p - 1) * (q - 1)
        if extended_gcd(e, phi)[0] == 1:
            return TeachingKeyPair(p * q, e, mod_inverse(e, phi), p, q)
    raise RuntimeError('RSA search exhausted its key-pair attempt budget')


def _representative(value, modulus, exponent):
    for name, item in (('representative', value), ('modulus', modulus), ('exponent', exponent)):
        _integer(item, name)
    if modulus < 9 or modulus % 2 == 0 or not 1 <= exponent < modulus:
        raise ValueError('Invalid RSA modulus or exponent')
    if not 0 <= value < modulus:
        raise ValueError('RSA representative must satisfy 0 <= value < modulus')


def encrypt_integer(message, n, e):
    """Textbook RSAEP integer primitive; deterministic and not secure encryption."""
    _representative(message, n, e)
    if e < 3 or e % 2 == 0:
        raise ValueError('Public exponent must be odd and >= 3')
    return mod_exp(message, e, n)


def decrypt_integer(ciphertext, n, d):
    """Textbook RSADP without padding, CRT or blinding; teaching use only."""
    _representative(ciphertext, n, d)
    return mod_exp(ciphertext, d, n)
