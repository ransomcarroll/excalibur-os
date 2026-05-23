from excalibur.text_utils import extract_json, slugify


def test_extract_json_plain():
    assert extract_json('{"groups": []}') == {"groups": []}


def test_extract_json_with_fence():
    raw = 'sure thing!\n```json\n{"groups": [{"name": "x", "issues": ["A-1"]}]}\n```\n'
    out = extract_json(raw)
    assert out["groups"][0]["name"] == "x"


def test_slugify():
    assert slugify("Add Payment Retry!") == "add-payment-retry"
    assert slugify("") == "shipment"
    assert len(slugify("a" * 100)) == 30
