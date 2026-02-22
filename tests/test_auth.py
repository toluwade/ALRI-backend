import uuid

import pytest

from app.utils.jwt import create_access_token, decode_token


def test_jwt_roundtrip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id)
    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert "exp" in payload


@pytest.mark.parametrize("bad", ["", "not-a-jwt", "a.b.c"])
def test_decode_bad_token_raises(bad):
    with pytest.raises(Exception):
        decode_token(bad)
