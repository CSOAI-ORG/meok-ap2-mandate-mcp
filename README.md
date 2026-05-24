# MEOK Google AP2 Mandate MCP

> ## 🧱 Part of the MEOK A2A Substrate (£999/mo)
> See [meok.ai/a2a](https://meok.ai/a2a).

# Google AP2 v0.2.0 — issue + verify + revoke signed spend authorisations

<!-- mcp-name: io.github.CSOAI-ORG/meok-ap2-mandate-mcp -->

[![PyPI](https://img.shields.io/pypi/v/meok-ap2-mandate-mcp)](https://pypi.org/project/meok-ap2-mandate-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## What this bridges

Google **AP2 (Agent Payments Protocol) v0.2.0** — the 60-org coalition spec (Mar 2026) for agentic commerce. AP2 introduces the **Mandate**: a signed user-issued authorisation telling an agent how much it may spend, where, for how long, with what SCA method.

AP2 mandates are the user-side counterpart to merchant-side **ACP** (Stripe ACP) and settlement-side **x402** (Coinbase). The full agentic-payment stack:

```
user → AP2 Mandate (this MCP)
     → Stripe ACP / Google AP2 Intent (agent-commerce-protocol-mcp)
     → x402 / card / SEPA (agent-x402-paywall-mcp)
     → Settlement + signed receipt (agent-commerce-payments-mcp)
```

This MCP also crosses-walks every mandate against **PSD2 Strong Customer Authentication** rules so EU operators get out-of-the-box regulatory compliance.

## Tools

| Tool | Purpose |
|---|---|
| `issue_mandate(user_did, agent_did, scope, cap_eur, window_hours, ...)` | Issue signed mandate |
| `verify_mandate(mandate_id, attempted_spend_eur, merchant_id?, category?)` | Pre-spend authorisation check |
| `consume_mandate(mandate_id, spend_eur)` | Deduct after successful payment |
| `revoke_mandate(mandate_id, reason)` | Immediate user-side revoke |
| `list_mandate_scopes()` | 7 AP2 scope categories + 5 SCA methods |
| `crosswalk_psd2(mandate_id, sca_method)` | PSD2 SCA strong/weak/exemption check |
| `sign_mandate_chain(mandate_id)` | HMAC-seal for audit chain |

## AP2 scope categories

`merchant_purchase` · `category_purchase` · `subscription_renewal` · `negotiation_only` · `search_only` · `data_request` · `agent_to_agent`

## PSD2 SCA methods

`passkey_webauthn` (FIDO2 strong) · `bank_app_push` (strong) · `totp_authenticator` (strong) · `sms_otp` (weak, fallback only) · `delegated_authority` (high-risk + audit)

## Sister MCPs

- `agent-commerce-protocol-mcp` — Stripe ACP + AP2 Intent + x402 bridge
- `agent-x402-paywall-mcp` — Coinbase HTTP 402 settlement
- `agent-commerce-payments-mcp` — PSD2 + MiCA payment rails
- `agent-policy-enforcement-mcp` — IAM gate for verify_mandate calls

Full catalogue: [meok.ai/anthropic-registry](https://meok.ai/anthropic-registry)

## Pricing

| Option | Price |
|---|---|
| Self-host MIT | £0 |
| Universal PAYG | £29/mo + £0.0002/call |
| A2A Substrate | £999/mo |
| Defence | £4,990/mo |

Buy: https://meok.ai/a2a

## Wire it up — full stack

Pair this with the MEOK chain that turns one agentic purchase into ONE signed compliance event:

1. **meok-ap2-mandate-mcp** — user signs spend authorisation
2. **agent-policy-enforcement-mcp** — agent's IAM gate
3. **agent-commerce-protocol-mcp** — ACP intent + AP2 mandate-bound transaction
4. **agent-x402-paywall-mcp** — on-chain settlement (or card via agent-commerce-payments-mcp)
5. **agent-audit-logger-mcp** — hash-chained evidence
6. **a2a-governance-bridge-mcp** — fold all attestations → 1 signed event

See [meok.ai/mcp-stack](https://meok.ai/mcp-stack) for architecture and [meok.ai/mcp-stack/demo](https://meok.ai/mcp-stack/demo) for the live demo.

## Licence

MIT. By [MEOK AI Labs](https://meok.ai) (CSOAI LTD, UK Companies House 16939677).
