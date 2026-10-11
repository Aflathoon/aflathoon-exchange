"""
Two-factor authentication helpers.

Uses TOTP (RFC 6238) — compatible with Google Authenticator, Authy,
1Password, Bitwarden, Aegis, and every other standard authenticator app.

Backup codes:
- 10 codes, each 10 chars (base32-ish, human friendly)
- Stored as bcrypt hashes in User.two_factor_backup_codes (JSON list)
- Each code is one-time-use: on success it's removed from the list
"""
import base64
import io
import json
import secrets
import string

import pyotp
import qrcode
from werkzeug.security import generate_password_hash, check_password_hash


ISSUER = "Aflathoon Exchange"


# ----------------------------------------------------------------- secret
def generate_secret() -> str:
    """Return a fresh base32 TOTP secret."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str, issuer: str = ISSUER) -> str:
    """Return the otpauth:// URI for QR codes."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def qr_png_data_uri(uri: str, box_size: int = 8) -> str:
    """Render the otpauth URI as a PNG and return as a data: URI."""
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ----------------------------------------------------------------- verify
def verify_code(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code. Allows ±1 window (30s) for clock drift."""
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


# ----------------------------------------------------------------- backup codes
_BACKUP_ALPHABET = string.ascii_uppercase + string.digits


def generate_backup_codes(count: int = 10, length: int = 10) -> list:
    """Human-friendly codes: 10 chars, uppercase + digits. Skip confusing chars."""
    alphabet = _BACKUP_ALPHABET.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    codes = []
    for _ in range(count):
        codes.append("".join(secrets.choice(alphabet) for _ in range(length)))
    return codes


def hash_backup_codes(codes: list) -> str:
    """Hash each code and return JSON-encoded list of hashes."""
    hashes = [generate_password_hash(c) for c in codes]
    return json.dumps(hashes)


def consume_backup_code(stored_json: str, candidate: str):
    """
    Check `candidate` against the stored hashes.
    Returns (matched: bool, new_json: str).
    If matched, the used hash is removed from the list.
    """
    if not stored_json:
        return False, stored_json
    try:
        hashes = json.loads(stored_json)
    except (ValueError, TypeError):
        return False, stored_json

    candidate = candidate.strip().upper().replace(" ", "").replace("-", "")
    for i, h in enumerate(hashes):
        if check_password_hash(h, candidate):
            remaining = hashes[:i] + hashes[i + 1:]
            return True, json.dumps(remaining)
    return False, stored_json


def remaining_backup_codes(stored_json: str) -> int:
    if not stored_json:
        return 0
    try:
        return len(json.loads(stored_json))
    except (ValueError, TypeError):
        return 0
