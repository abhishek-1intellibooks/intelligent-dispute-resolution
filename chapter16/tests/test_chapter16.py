import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from mandate import Cart, check_purchase, customer_key, sign_mandate, worked_example  # noqa: E402


def _mandate(**kw):
    sk = customer_key("CUST-T")
    args = dict(max_total=150.0, categories={"headphones"}, confirm_above=135.0,
                expires_at=datetime(2026, 12, 31))
    args.update(kw)
    return sk, sign_mandate(sk, "CUST-T", "AGENT-1", **args)


def test_valid_purchase_has_no_reasons():
    sk, m = _mandate()
    cart = Cart("AGENT-1", 99.0, "headphones", datetime(2026, 11, 1), False)
    assert check_purchase(m, cart, sk.public_key()) == []


def test_each_limit_is_checked():
    sk, m = _mandate()
    cart = Cart("AGENT-2", 249.0, "travel", datetime(2027, 1, 2), False)
    assert len(check_purchase(m, cart, sk.public_key())) == 5


def test_signature_from_another_key_fails():
    sk, m = _mandate()
    other = customer_key("SOMEONE-ELSE").public_key()
    cart = Cart("AGENT-1", 99.0, "headphones", datetime(2026, 11, 1), False)
    assert check_purchase(m, cart, other) == ["the mandate's signature is not the customer's"]


def test_worked_example_reasons():
    assert worked_example() == ["total 249.00 over the limit of 150.00",
                                "no customer confirmation where the mandate required one"]


def test_fallback_matches_rfc8032_test_vector_1():
    import ed25519_fallback as f
    sk = f.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"))
    assert sk.public_key().public_bytes_raw().hex() == \
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    sig = sk.sign(b"")
    assert sig.hex() == ("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
                         "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
    sk.public_key().verify(sig, b"")
    with pytest.raises(f.InvalidSignature):
        sk.public_key().verify(sig, b"x")


def test_roadmap_has_phases_with_checks():
    rm = yaml.safe_load((HERE / "roadmap.yaml").read_text(encoding="utf-8"))
    assert [p["name"] for p in rm["phases"]] == ["Foundation", "Decide", "Read and write", "Act",
                                                 "Scale and govern"]
    assert all(c["check"] for p in rm["phases"] for c in p["exit_criteria"])


def test_config_keys_are_known_parameters():
    import run_month
    platform = run_month.Platform.from_config("config/production-like.yaml")
    assert platform.p["PLATFORM_COST_PER_CLAIM"] == 0.118


def test_small_month_runs_and_audit_detects_tampering(tmp_path):
    import run_month
    path = tmp_path / "small.jsonl"
    run_month.make_month(path, n=2_000)
    table = run_month.run_month(path=str(path))
    platform, baseline, results = run_month.run_month.details
    assert platform.audit.verify() is None
    assert table.loc["Analyst minutes per claim", "Manual baseline"] == "25.0"
    assert max(r["days"] for r in results) <= 14
    platform.audit.entries[10]["record"]["ending"] = "edited"
    assert platform.audit.verify() == 10
