"""签名算法单测：与独立实现（Node 版前端逻辑复刻）的固定向量交叉校验。"""

from __future__ import annotations

from huyou_mcp.crypto import new_nonce, sign_params

# 参考向量由 _recon/sigvec.mjs（直接照抄前端 Hi() 的 Node 实现）生成
VECTOR_1 = {
    "params": {"circle_id": "796893005792620800", "count": 20, "tpl": "1,2,3,4,26"},
    "headers": {"s-nonce": "abc123", "S-VS": "6.24.0"},
    "now_ms": 1794717000000,
    "sig": "6201cf2543f52e998e7abc1caea34f0e",
}
VECTOR_2 = {
    "params": {"feed_id": "1497670320637805952", "count": 20},
    "headers": {"s-nonce": "deadbeef", "S-VS": "6.24.0"},
    "now_ms": 1794718000123,
    "sig": "990fbae59b83ec100caeee6cb72ea356",
}


def test_sign_vector_1():
    out = sign_params(VECTOR_1["params"], VECTOR_1["headers"], now_ms=VECTOR_1["now_ms"])
    assert out["sig"] == VECTOR_1["sig"]
    assert out["flyer"] == VECTOR_1["now_ms"]
    assert out["appid"] == 330012
    assert out["app_key_vs"] == "6.24.0"


def test_sign_vector_2():
    out = sign_params(VECTOR_2["params"], VECTOR_2["headers"], now_ms=VECTOR_2["now_ms"])
    assert out["sig"] == VECTOR_2["sig"]


def test_none_values_are_dropped_and_excluded_from_signature():
    with_none = sign_params(
        {"a": 1, "b": None}, {"s-nonce": "n1", "S-VS": "6.24.0"}, now_ms=1
    )
    without_none = sign_params({"a": 1}, {"s-nonce": "n1", "S-VS": "6.24.0"}, now_ms=1)
    assert "b" not in with_none
    assert with_none["sig"] == without_none["sig"]


def test_signature_is_idempotent():
    first = sign_params({"a": 1}, {"s-nonce": "n", "S-VS": "6.24.0"}, now_ms=5)
    second = sign_params(first, {"s-nonce": "n", "S-VS": "6.24.0"}, now_ms=9)
    assert second == first


def test_bool_serialization_matches_javascript():
    # JS 里 String(true) === "true"，Python 默认是 "True"，签名必须按 JS 来
    out = sign_params({"b": True}, {"s-nonce": "n", "S-VS": "6.24.0"}, now_ms=1)
    assert out["b"] is True
    assert len(out["sig"]) == 32


def test_nonce_shape():
    nonce = new_nonce()
    assert len(nonce) == 32
    int(nonce, 16)  # 必须是纯 16 进制


def test_float_cursor_is_stringified_like_javascript():
    """翻页游标从 JSON 读出来是 float，签名与请求必须都用 "-1794717435133" 这种形式。"""
    from huyou_mcp.crypto import js_str

    out = sign_params({"score": -1794717435133.0}, {"s-nonce": "n", "S-VS": "6.24.0"}, now_ms=1)
    assert js_str(out["score"]) == "-1794717435133"
    as_int = sign_params({"score": -1794717435133}, {"s-nonce": "n", "S-VS": "6.24.0"}, now_ms=1)
    assert out["sig"] == as_int["sig"]
