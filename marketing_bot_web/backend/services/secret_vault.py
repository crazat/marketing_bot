"""
Secret Vault — Windows DPAPI + Linux/Mac fallback (Phase 1.2 / R23)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

목적: config/secrets.json 평문 → DPAPI 암호화 (Windows). 1건 침해 = secrets·DB 통째 노출 risk 차단.

핵심 정찰 (R23):
- 의원급 침해 91건 중 47% (가장 취약)
- secrets.json 평문 = CRITICAL
- 한국 PIPA 보건의료 가이드라인 2024-12 강화

DPAPI 동작:
- CryptProtectData / CryptUnprotectData
- 현재 Windows 사용자 + 머신 둘 다 묶음 (CRYPTPROTECT_LOCAL_MACHINE 옵션 X = 사용자 묶음)
- 사용자 password 잠겨도 해당 사용자로 로그인하면 자동 unlock

암호화 형식 — `secrets.json.enc`:
{
    "version": 1,
    "platform": "windows_dpapi",
    "encrypted_at": "2026-05-25T13:30:00",
    "ciphertext_b64": "..."
}

Linux/Mac fallback:
- AES-256-GCM + PBKDF2 (env RECOVER_VAULT_PASS 또는 prompt)
- 또는 OS keychain (macOS Keychain·Linux Secret Service) — 추가 구현 시점

사용법:
    from services.secret_vault import vault
    vault.encrypt_to_file("config/secrets.json", "config/secrets.json.enc")
    secrets = vault.read("config/secrets.json.enc")
    codex_bin = secrets.get("CODEX_CLI_BIN", "codex")
"""

from __future__ import annotations
import os, sys, json, base64, sqlite3, getpass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DB_PATH = Path(os.getenv("MARKETING_BOT_DB_PATH") or os.getenv("APP_DB_PATH") or PROJECT_ROOT / "db" / "marketing_data.db")

IS_WINDOWS = sys.platform == "win32"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Windows DPAPI (CryptProtectData via ctypes)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _dpapi_encrypt(plaintext: bytes) -> bytes:
    if not IS_WINDOWS:
        raise RuntimeError("DPAPI Windows only")
    import ctypes
    from ctypes import wintypes
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
    in_blob = DATA_BLOB(len(plaintext), ctypes.cast(ctypes.c_char_p(plaintext), ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
    if not ok:
        raise OSError(f"CryptProtectData failed: {ctypes.get_last_error()}")
    try:
        ciphertext = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return ciphertext


def _dpapi_decrypt(ciphertext: bytes) -> bytes:
    if not IS_WINDOWS:
        raise RuntimeError("DPAPI Windows only")
    import ctypes
    from ctypes import wintypes
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
    in_blob = DATA_BLOB(len(ciphertext), ctypes.cast(ctypes.c_char_p(ciphertext), ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
    if not ok:
        raise OSError(f"CryptUnprotectData failed: {ctypes.get_last_error()}")
    try:
        plaintext = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return plaintext


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cross-platform AES fallback (Linux/Mac, env password)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _aes_encrypt(plaintext: bytes, password: str) -> bytes:
    """AES-256-GCM + PBKDF2-SHA256. salt(16) + nonce(12) + tag(16) + ciphertext."""
    try:
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise RuntimeError("pip install cryptography (Linux/Mac fallback)")
    salt = os.urandom(16)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000)
    key = kdf.derive(password.encode("utf-8"))
    aes = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aes.encrypt(nonce, plaintext, None)
    return salt + nonce + ciphertext


def _aes_decrypt(blob: bytes, password: str) -> bytes:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce, ciphertext = blob[:16], blob[16:28], blob[28:]
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000)
    key = kdf.derive(password.encode("utf-8"))
    aes = AESGCM(key)
    return aes.decrypt(nonce, ciphertext, None)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Audit log (R23 audit hook)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _audit(event_type: str, target: str, severity: str = "info", details: Optional[Dict] = None):
    try:
        with sqlite3.connect(str(DB_PATH), timeout=5.0) as conn:
            conn.execute(
                """INSERT INTO recover_security_audit (event_type, actor, target, details_json, severity)
                   VALUES (?, ?, ?, ?, ?)""",
                (event_type, "secret_vault", target,
                 json.dumps(details or {}, ensure_ascii=False), severity),
            )
            conn.commit()
    except Exception:
        pass  # audit failure는 main flow 차단 X


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SecretVault:
    """플랫폼별 자동 라우팅 — Windows DPAPI / Linux·Mac AES."""

    def __init__(self):
        self.platform = "windows_dpapi" if IS_WINDOWS else "aes_pbkdf2"

    def encrypt_to_file(self, plain_path: str, encrypted_path: str) -> Dict[str, Any]:
        plain_p = Path(plain_path)
        enc_p = Path(encrypted_path)
        if not plain_p.exists():
            return {"_error": f"plain file not found: {plain_path}"}
        plaintext = plain_p.read_bytes()
        if IS_WINDOWS:
            ciphertext = _dpapi_encrypt(plaintext)
        else:
            password = os.getenv("RECOVER_VAULT_PASS") or getpass.getpass("Vault password: ")
            ciphertext = _aes_encrypt(plaintext, password)
        envelope = {
            "version": 1,
            "platform": self.platform,
            "encrypted_at": datetime.now().isoformat(timespec="seconds"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        }
        enc_p.parent.mkdir(parents=True, exist_ok=True)
        enc_p.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        _audit("secret_encrypted", str(enc_p), "info",
               {"source": str(plain_p), "size": len(plaintext)})
        return {"encrypted_path": str(enc_p), "platform": self.platform,
                "size_bytes": len(ciphertext),
                "_recommendation": "원본 평문 파일은 즉시 삭제 후 .gitignore 추가"}

    def read(self, encrypted_path: str) -> Dict[str, Any]:
        enc_p = Path(encrypted_path)
        if not enc_p.exists():
            return {}
        envelope = json.loads(enc_p.read_text(encoding="utf-8"))
        if envelope.get("version") != 1:
            raise ValueError("unsupported vault version")
        ciphertext = base64.b64decode(envelope["ciphertext_b64"])
        platform_used = envelope.get("platform")
        if platform_used == "windows_dpapi" and IS_WINDOWS:
            plaintext = _dpapi_decrypt(ciphertext)
        elif platform_used == "aes_pbkdf2":
            password = os.getenv("RECOVER_VAULT_PASS") or getpass.getpass("Vault password: ")
            plaintext = _aes_decrypt(ciphertext, password)
        else:
            raise RuntimeError(f"platform mismatch: file={platform_used} runtime={self.platform}")
        _audit("secret_read", str(enc_p), "info")
        return json.loads(plaintext.decode("utf-8"))

    def get(self, key: str, encrypted_path: str = "config/secrets.json.enc",
            default: Any = None) -> Any:
        try:
            data = self.read(encrypted_path)
            return data.get(key, default)
        except Exception as e:
            _audit("secret_read_failed", encrypted_path, "high", {"error": str(e)[:100]})
            return default


vault = SecretVault()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--encrypt", nargs=2, metavar=("PLAIN", "ENC"),
                   help="encrypt plaintext file to encrypted file")
    p.add_argument("--read", help="read encrypted file and dump (TESTING ONLY)")
    p.add_argument("--test", action="store_true", help="round-trip test")
    args = p.parse_args()

    if args.test:
        # round-trip
        tmp_plain = PROJECT_ROOT / "config" / "_vault_test_plain.json"
        tmp_enc = PROJECT_ROOT / "config" / "_vault_test.enc"
        tmp_plain.parent.mkdir(parents=True, exist_ok=True)
        tmp_plain.write_text(json.dumps({"TEST_KEY": "secret_value_xyz123"}), encoding="utf-8")
        r1 = vault.encrypt_to_file(str(tmp_plain), str(tmp_enc))
        print(f"encrypted: {r1}")
        r2 = vault.read(str(tmp_enc))
        assert r2.get("TEST_KEY") == "secret_value_xyz123", "round-trip failed"
        print(f"decrypted OK: {r2}")
        tmp_plain.unlink()
        tmp_enc.unlink()
        print("[OK] DPAPI round-trip PASS")
    elif args.encrypt:
        print(json.dumps(vault.encrypt_to_file(args.encrypt[0], args.encrypt[1]),
                         ensure_ascii=False, indent=2))
    elif args.read:
        print(json.dumps(vault.read(args.read), ensure_ascii=False, indent=2))
    else:
        print(f"platform: {vault.platform}")
        print("usage: --test | --encrypt PLAIN ENC | --read ENC")
