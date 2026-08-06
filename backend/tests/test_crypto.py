from app.core.crypto import decrypt_token, encrypt_token


def test_roundtrip():
    enc = encrypt_token("EAAsecret")
    assert enc != "EAAsecret"
    assert decrypt_token(enc) == "EAAsecret"
