"""Smoke tests for meok-ap2-mandate-mcp."""
import sys, os, inspect, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (
    issue_mandate,
    verify_mandate,
    consume_mandate,
    revoke_mandate,
    list_mandate_scopes,
    crosswalk_psd2,
    sign_mandate_chain,
    _MANDATES,
)


def test_issue_mandate_basic():
    _MANDATES.clear()
    r = issue_mandate("did:web:user.example", "did:web:agent.example", "merchant_purchase", 250.0, 24, merchant_id="acme_widgets")
    assert r["mandate"]["mandate_id"].startswith("AP2_")
    assert r["mandate"]["cap_eur"] == 250.0
    assert r["mandate"]["psd2_compliant"] is True


def test_issue_mandate_unknown_scope():
    r = issue_mandate("u", "a", "fake_scope", 100.0)
    assert "error" in r


def test_issue_mandate_unknown_sca():
    r = issue_mandate("u", "a", "category_purchase", 50.0, sca_method="telepathy")
    assert "error" in r


def test_issue_mandate_zero_cap():
    r = issue_mandate("u", "a", "data_request", 0)
    assert "error" in r


def test_verify_within_cap():
    _MANDATES.clear()
    m = issue_mandate("u", "a", "category_purchase", 100.0, category="books")
    r = verify_mandate(m["mandate"]["mandate_id"], 30.0, category="books")
    assert r["allowed"] is True


def test_verify_over_cap():
    _MANDATES.clear()
    m = issue_mandate("u", "a", "category_purchase", 100.0)
    r = verify_mandate(m["mandate"]["mandate_id"], 500.0)
    assert r["allowed"] is False
    assert r["reason"] == "cap_exceeded"


def test_verify_merchant_mismatch():
    _MANDATES.clear()
    m = issue_mandate("u", "a", "merchant_purchase", 100.0, merchant_id="merchant_a")
    r = verify_mandate(m["mandate"]["mandate_id"], 20.0, merchant_id="merchant_b")
    assert r["allowed"] is False


def test_verify_unknown_mandate():
    r = verify_mandate("AP2_fake_id", 10.0)
    assert r["allowed"] is False


def test_consume_reduces_remaining():
    _MANDATES.clear()
    m = issue_mandate("u", "a", "data_request", 50.0)
    c = consume_mandate(m["mandate"]["mandate_id"], 30.0)
    assert c["ok"] is True
    assert abs(c["remaining_eur"] - 20.0) < 0.01


def test_consume_exhausts_mandate():
    _MANDATES.clear()
    m = issue_mandate("u", "a", "data_request", 50.0)
    consume_mandate(m["mandate"]["mandate_id"], 50.0)
    r = verify_mandate(m["mandate"]["mandate_id"], 1.0)
    # After exhaustion the mandate status flips
    assert r["allowed"] is False or _MANDATES[m["mandate"]["mandate_id"]]["status"] == "exhausted"


def test_revoke_mandate():
    _MANDATES.clear()
    m = issue_mandate("u", "a", "data_request", 50.0)
    r = revoke_mandate(m["mandate"]["mandate_id"], "user_changed_mind")
    assert r["revoked"] is True
    v = verify_mandate(m["mandate"]["mandate_id"], 1.0)
    assert v["allowed"] is False


def test_list_scopes_has_7():
    r = list_mandate_scopes()
    assert len(r["scopes"]) == 7
    assert "passkey_webauthn" in r["sca_methods"]


def test_crosswalk_psd2_strong():
    _MANDATES.clear()
    m = issue_mandate("u", "a", "data_request", 1000.0, sca_method="passkey_webauthn")
    r = crosswalk_psd2(m["mandate"]["mandate_id"], "passkey_webauthn")
    assert r["psd2_compliant"] is True


def test_crosswalk_psd2_low_value_exemption():
    _MANDATES.clear()
    m = issue_mandate("u", "a", "data_request", 25.0, sca_method="sms_otp")
    r = crosswalk_psd2(m["mandate"]["mandate_id"], "sms_otp")
    assert r["exemption_applicable"] is True


def test_sign_chain():
    _MANDATES.clear()
    m = issue_mandate("u", "a", "data_request", 25.0)
    r = sign_mandate_chain(m["mandate"]["mandate_id"])
    assert "signature" in r


if __name__ == "__main__":
    g = dict(globals())
    fns = [v for k, v in g.items() if k.startswith("test_") and inspect.isfunction(v)]
    p = f = 0
    for fn in fns:
        try:
            fn(); print(f"OK {fn.__name__}"); p += 1
        except Exception as e:
            print(f"X  {fn.__name__}: {type(e).__name__}: {e}"); traceback.print_exc(); f += 1
    print(f"\n{p} passed, {f} failed")
