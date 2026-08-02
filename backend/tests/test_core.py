import jwt

from app.main import ALGORITHM, JWT_SECRET, create_token, normalize_conversation_analysis, parse_json_content, password_hash


def test_password_hash_is_not_plaintext_and_verifies():
    raw = "StrongPassword-2026"
    encoded = password_hash.hash(raw)
    assert encoded != raw
    assert password_hash.verify(raw, encoded)
    assert not password_hash.verify("wrong-password", encoded)


def test_access_token_contains_numeric_subject():
    token = create_token(42)
    payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    assert payload["sub"] == "42"
    assert "exp" in payload


def test_json_parser_accepts_plain_and_fenced_json():
    assert parse_json_content('{"name":"Ada"}') == {"name": "Ada"}
    assert parse_json_content('```json\n{"score":88}\n```') == {"score": 88}


def test_qwen_analysis_is_normalized_and_summary_is_bounded():
    result = normalize_conversation_analysis({"summary": "客" * 120, "interests": ["GPU", ""], "score": 108, "next_action": "发送方案", "evidence": ["需要GPU服务器"]})
    assert len(result["summary"]) == 100
    assert result["score"] == 100
    assert result["interests"] == ["GPU"]
