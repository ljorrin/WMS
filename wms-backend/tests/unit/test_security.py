"""Tests unitarios — módulo de seguridad."""

import pytest
from jose import JWTError

from app.core.security import (
    hash_password, verify_password, needs_rehash,
    create_access_token, create_refresh_token,
    decode_access_token, decode_refresh_token,
    generate_api_key, mask_sensitive,
)
import uuid


class TestPasswordHashing:
    def test_hash_is_not_plain_text(self):
        hashed = hash_password("mypassword")
        assert hashed != "mypassword"
        assert hashed.startswith("$2b$")

    def test_verify_correct_password(self):
        hashed = hash_password("correctpassword")
        assert verify_password("correctpassword", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_two_hashes_are_different(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2  # Bcrypt usa salt aleatorio


class TestJWT:
    def test_access_token_roundtrip(self):
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        token = create_access_token(user_id, tenant_id)
        payload = decode_access_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["tid"] == str(tenant_id)
        assert payload["typ"] == "access"

    def test_refresh_token_roundtrip(self):
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        token = create_refresh_token(user_id, tenant_id)
        payload = decode_refresh_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["typ"] == "refresh"

    def test_wrong_token_type_raises(self):
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        access_token = create_access_token(user_id, tenant_id)
        with pytest.raises(JWTError):
            decode_refresh_token(access_token)  # Access token no es refresh

    def test_tampered_token_raises(self):
        token = create_access_token(uuid.uuid4(), uuid.uuid4())
        tampered = token[:-5] + "xxxxx"
        with pytest.raises(JWTError):
            decode_access_token(tampered)


class TestUtilities:
    def test_generate_api_key_format(self):
        key = generate_api_key("wms")
        assert key.startswith("wms_")
        assert len(key) == 4 + 64  # "wms_" (4) + 32 bytes hex (64) = 68 chars

    def test_mask_sensitive(self):
        assert mask_sensitive("mypassword123", visible_chars=3) == "**********123"
        assert mask_sensitive("ab") == "****"
