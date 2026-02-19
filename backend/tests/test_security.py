from app.core.security import decrypt_secret, encrypt_secret, mask_secret


def test_encrypt_and_decrypt_roundtrip() -> None:
    raw = 'sk-test-123456'
    encrypted = encrypt_secret(raw)
    assert encrypted != raw
    assert decrypt_secret(encrypted) == raw


def test_mask_secret() -> None:
    masked = mask_secret('abcdefghijk')
    assert masked.startswith('abc')
    assert masked.endswith('ijk')
