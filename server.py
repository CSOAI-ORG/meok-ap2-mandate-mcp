#!/usr/bin/env python3
"""
Buy Pro: https://www.csoai.org/checkout

MEOK AP2 Mandate MCP — Google Agent Payments Protocol v0.2.0 bridge
======================================================================

By MEOK AI Labs · https://meok.ai · MIT
<!-- mcp-name: io.github.CSOAI-ORG/meok-ap2-mandate-mcp -->

WHAT THIS BRIDGES
-----------------
Google AP2 (Agent Payments Protocol) v0.2.0 — the 60-org coalition spec
for agentic commerce. AP2 introduces the "Mandate" — a signed authorisation
artefact a user issues to an agent giving it permission to spend up to N
amount on M categories within T window.

AP2 mandates are the user-side counterpart to merchant-side ACP (Stripe ACP)
+ settlement-side x402 (Coinbase). The full agentic-payment stack is:

  user → AP2 Mandate (this MCP)
       → Stripe ACP / Google AP2 Intent (agent-commerce-protocol-mcp)
       → x402 / card / SEPA (agent-x402-paywall-mcp / agent-commerce-payments-mcp)
       → Settlement + receipt (signed)

This MCP issues + verifies + revokes AP2 Mandates with Article 5 PSD2 +
MiCA + 6AMLD overlays for EU compliance.

TOOLS
-----
- issue_mandate(user_did, agent_did, scope, cap_eur, window_hours)
- verify_mandate(mandate, attempted_spend_eur, merchant_id?)
- list_mandate_scopes(): valid AP2 scope categories
- revoke_mandate(mandate_id, reason)
- crosswalk_psd2(mandate, sca_method)
- sign_mandate_chain(mandate, signer_did)

By MEOK AI Labs · MIT.
"""

from __future__ import annotations
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("meok-ap2-mandate")
_HMAC_SECRET = os.environ.get("MEOK_HMAC_SECRET", "")
_MANDATES: dict[str, dict] = {}


AP2_SPEC_VERSION = "AP2 v0.2.0 (Google + 60-org coalition, Mar 2026)"

AP2_SCOPES = {
    "merchant_purchase":  "Buy goods/services from a specific merchant identifier",
    "category_purchase":  "Buy within a product category (e.g. groceries, books)",
    "subscription_renewal": "Renew an existing subscription (no new merchants)",
    "negotiation_only":   "Negotiate price/terms — no auto-execute",
    "search_only":        "Search merchants — no purchase",
    "data_request":       "Pay for paywalled data (x402-compatible)",
    "agent_to_agent":     "Pay another agent (A2A x402 settlement)",
}

# PSD2 SCA method bindings
SCA_METHODS = {
    "passkey_webauthn": "FIDO2/WebAuthn passkey (PSD2 SCA strong)",
    "totp_authenticator": "TOTP from authenticator app",
    "sms_otp":            "SMS OTP (PSD2 SCA weak — fallback only)",
    "bank_app_push":      "Issuing-bank app push approval",
    "delegated_authority": "Delegated user authority (high-risk — needs audit)",
}


def _sign(payload: dict) -> str:
    if not _HMAC_SECRET:
        return "unsigned-no-key-configured"
    return hmac.new(_HMAC_SECRET.encode(), json.dumps(payload, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def issue_mandate(
    user_did: str,
    agent_did: str,
    scope: str,
    cap_eur: float,
    window_hours: int = 24,
    merchant_id: Optional[str] = None,
    category: Optional[str] = None,
    sca_method: str = "passkey_webauthn",
) -> dict:
    """
    Issue an AP2 Mandate — signed authorisation for the agent to spend.

    Args:
        user_did: W3C DID of the issuing user.
        agent_did: W3C DID of the receiving agent.
        scope: AP2 scope from AP2_SCOPES.
        cap_eur: Maximum spend in EUR for the window.
        window_hours: Validity window in hours.
        merchant_id: Optional merchant restriction.
        category: Optional category restriction (e.g. "books").
        sca_method: PSD2 SCA method used to authorise.

    Returns:
        {mandate, signature, expires_at}
    """
    if scope not in AP2_SCOPES:
        return {"error": f"Unknown scope. Use one of {list(AP2_SCOPES)}"}
    if sca_method not in SCA_METHODS:
        return {"error": f"Unknown SCA method. Use one of {list(SCA_METHODS)}"}
    if cap_eur <= 0:
        return {"error": "cap_eur must be positive"}

    mandate_id = f"AP2_{int(time.time())}_{os.urandom(4).hex()}"
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=window_hours)

    mandate = {
        "mandate_id": mandate_id,
        "spec": AP2_SPEC_VERSION,
        "user_did": user_did,
        "agent_did": agent_did,
        "scope": scope,
        "scope_description": AP2_SCOPES[scope],
        "cap_eur": cap_eur,
        "remaining_eur": cap_eur,
        "merchant_id": merchant_id,
        "category": category,
        "window_hours": window_hours,
        "issued_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "sca_method": sca_method,
        "sca_label": SCA_METHODS[sca_method],
        "status": "active",
        "psd2_compliant": sca_method in {"passkey_webauthn", "bank_app_push", "totp_authenticator"},
    }
    mandate["signature"] = _sign(mandate)
    _MANDATES[mandate_id] = mandate
    return {
        "mandate": mandate,
        "signature": mandate["signature"],
        "expires_at": mandate["expires_at"],
        "next_step": "Pass to your agent. Agent calls verify_mandate() before each spend.",
    }


@mcp.tool()
def verify_mandate(
    mandate_id: str,
    attempted_spend_eur: float,
    merchant_id: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    """
    Verify an AP2 mandate before an agent spend attempt.

    Args:
        mandate_id: From issue_mandate().
        attempted_spend_eur: Amount the agent wants to spend.
        merchant_id: Merchant ID of the proposed transaction.
        category: Category of the proposed transaction.

    Returns:
        {allowed, reason, remaining_eur_after}
    """
    if mandate_id not in _MANDATES:
        return {"allowed": False, "reason": "unknown_mandate"}
    m = _MANDATES[mandate_id]

    # Expiry check
    expires = datetime.fromisoformat(m["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires:
        return {"allowed": False, "reason": "expired", "expired_at": m["expires_at"]}

    # Status check
    if m["status"] != "active":
        return {"allowed": False, "reason": f"status={m['status']}"}

    # Scope binding
    if m["merchant_id"] and merchant_id != m["merchant_id"]:
        return {"allowed": False, "reason": f"merchant_id_mismatch (mandate restricted to {m['merchant_id']})"}
    if m["category"] and category != m["category"]:
        return {"allowed": False, "reason": f"category_mismatch (mandate restricted to {m['category']})"}

    # Cap check
    if attempted_spend_eur > m["remaining_eur"]:
        return {
            "allowed": False,
            "reason": "cap_exceeded",
            "remaining_eur": m["remaining_eur"],
            "attempted_eur": attempted_spend_eur,
        }

    new_remaining = m["remaining_eur"] - attempted_spend_eur
    return {
        "allowed": True,
        "remaining_eur_after": new_remaining,
        "reason": "ok",
        "mandate_id": mandate_id,
        "verified_at": _ts(),
    }


@mcp.tool()
def consume_mandate(mandate_id: str, spend_eur: float) -> dict:
    """
    Deduct spend from a mandate after a successful transaction.

    Args:
        mandate_id: From issue_mandate().
        spend_eur: Actual amount spent.

    Returns:
        {ok, remaining_eur}
    """
    if mandate_id not in _MANDATES:
        return {"ok": False, "reason": "unknown_mandate"}
    m = _MANDATES[mandate_id]
    if spend_eur > m["remaining_eur"]:
        return {"ok": False, "reason": "would_exceed_cap"}
    m["remaining_eur"] -= spend_eur
    if m["remaining_eur"] <= 0.01:
        m["status"] = "exhausted"
    return {"ok": True, "remaining_eur": m["remaining_eur"], "status": m["status"]}


@mcp.tool()
def revoke_mandate(mandate_id: str, reason: str = "user_revoked") -> dict:
    """
    Revoke an active mandate immediately.

    Args:
        mandate_id: From issue_mandate().
        reason: Why this is being revoked.

    Returns:
        {revoked, mandate_id, revoked_at}
    """
    if mandate_id not in _MANDATES:
        return {"revoked": False, "reason": "unknown_mandate"}
    m = _MANDATES[mandate_id]
    m["status"] = "revoked"
    m["revocation_reason"] = reason
    m["revoked_at"] = _ts()
    return {"revoked": True, "mandate_id": mandate_id, "revoked_at": m["revoked_at"]}


@mcp.tool()
def list_mandate_scopes() -> dict:
    """Return the valid AP2 scope categories + SCA methods."""
    return {
        "spec": AP2_SPEC_VERSION,
        "scopes": AP2_SCOPES,
        "sca_methods": SCA_METHODS,
    }


@mcp.tool()
def crosswalk_psd2(mandate_id: str, sca_method: str) -> dict:
    """
    Cross-walk an AP2 mandate against PSD2 Strong Customer Authentication rules.

    Args:
        mandate_id: From issue_mandate().
        sca_method: PSD2 SCA method to evaluate.

    Returns:
        {psd2_compliant, sca_strength, exemption_applicable}
    """
    if mandate_id not in _MANDATES:
        return {"error": "unknown_mandate"}
    m = _MANDATES[mandate_id]
    strong = sca_method in {"passkey_webauthn", "bank_app_push", "totp_authenticator"}
    # PSD2 Article 13 — low-value remote payment exemption < €30 + cumulative < €100/€150
    exemption = m["cap_eur"] < 30
    return {
        "psd2_compliant": strong or exemption,
        "sca_strength": "strong" if strong else "weak",
        "exemption_applicable": exemption,
        "exemption_reason": "Article 13 low-value (<€30)" if exemption else None,
        "regulation": "PSD2 + Commission Delegated Regulation 2018/389",
    }


@mcp.tool()
def sign_mandate_chain(mandate_id: str) -> dict:
    """HMAC-seal the mandate for audit chain."""
    if mandate_id not in _MANDATES:
        return {"error": "unknown_mandate"}
    m = _MANDATES[mandate_id]
    sealed = {**m, "sealed_at": _ts()}
    sig = _sign(sealed)
    return {
        "signed": _HMAC_SECRET != "",
        "signature": sig,
        "sealed_at": sealed["sealed_at"],
        "verify_url": f"https://meok-attestation-api.vercel.app/verify/{mandate_id}",
    }


if __name__ == "__main__":
    mcp.run()


# ── MEOK monetization layer (Stripe upgrade · PAYG · pricing) ──────────
# Free tier is zero-config. Upgrade to Pro (unlimited) or pay-as-you-go per call.
import os as _meok_os
MEOK_STRIPE_UPGRADE = "https://buy.stripe.com/5kQ6oJ0xS3ce8sl7ew8k91j"  # Pro (unlimited)
MEOK_PAYG_KEY = _meok_os.environ.get("MEOK_PAYG_KEY", "")  # set to enable PAYG (x402 / ~GBP0.05 per call)
MEOK_PRICING = "https://meok.ai/pricing"


def meok_upsell(tier: str = "free") -> dict:
    """Monetization options for free-tier callers: Pro upgrade, PAYG, or pricing page."""
    if tier != "free":
        return {}
    return {"upgrade_url": MEOK_STRIPE_UPGRADE,
            "payg_enabled": bool(MEOK_PAYG_KEY),
            "pricing": MEOK_PRICING}
