# Security Policy

OpenSplit is a self-hosted, non-custodial Bitcoin revenue-sharing tool built on
BTCPay Server. This document describes its actual threat model — including the
parts that are not pretty — so you can decide how to deploy it and how to
report problems.

## Trust model

**Your machine is the trust root.** OpenSplit runs on infrastructure you
control (typically Docker Compose on your own server). There is no hosted
service, no telemetry, and no third party in the loop other than the BTCPay
Server instance you connect it to.

**OpenSplit is non-custodial.** It never holds funds or private keys. All
money movement happens inside your BTCPay Server (and its wallet/Lightning
node). OpenSplit computes splits and instructs BTCPay to create payouts.

**But: OpenSplit holds a spend-capable BTCPay API key.** "Non-custodial" does
not mean "harmless if compromised." The Greenfield API key OpenSplit stores can
create and approve payouts via pull payments — an attacker who obtains it can
drain funds through your BTCPay store's payout path. Treat the machine running
OpenSplit with the same care as the machine running BTCPay itself.

## Known design facts (v0.1.x)

These are deliberate, documented trade-offs in the current version. They are
not vulnerabilities to report; they are facts to plan around.

### BTCPay credentials are stored in plaintext

The BTCPay Greenfield API key and the webhook secret are stored **in plaintext
in the PostgreSQL database**. There is no application-level encryption at rest.
Anyone who can read the database can spend via BTCPay payouts.

Mitigations in place and expected of the operator:

- OpenSplit requests only the **minimal Greenfield permissions** it uses:
  - `btcpay.store.cancreateinvoice`
  - `btcpay.store.canviewinvoices`
  - `btcpay.store.canmanagepullpayments`
  - `btcpay.store.canviewstoresettings`

  Notably absent: wallet access, server admin, store modification. The blast
  radius of a leaked key is limited to invoice creation and the pull-payment /
  payout surface — which is still spend-capable, hence the warnings above.
- Keep the Postgres instance private (no publicly exposed port, strong
  password, container network only).
- Restrict shell and Docker access to the server; anyone with `docker exec` or
  a DB dump has the key.
- Credentials are **redacted in the UI, API responses, and logs** — plaintext
  exists only in the database.

### Single-tenant email/password login, no 2FA

The dashboard login is a single-tenant email/password. There is no
two-factor authentication, no account lockout policy, and no session
management UI. Do not expose the dashboard to the public internet without an
additional layer (VPN, reverse-proxy auth, IP allowlist).

### Public proof pages are privacy-safe by default

Public Split Proof pages show split structure and payout status but **hide
amounts unless the operator explicitly opts in**. Credentials and internal
identifiers are never shown. Privacy regressions on these pages are in scope
for security reports (see below).

### Nostr key handling (signed Split Proofs)

Signed Split Proofs use the team's Nostr key. The custody rules are strict:

- **The private key is never stored in the database** — not encrypted, not
  hashed, not anywhere. It is supplied by the self-hosted operator via the
  `ORCHESTRATOR_NOSTR_SECKEY` environment variable (nsec or hex) and exists
  only in process memory at signing time. Protecting that environment
  (compose files, shell history, process listings) is the **operator's
  responsibility**, exactly like the JWT secret.
- Only the team's **public** key (npub/hex) is stored, as
  `tenants.nostr_pubkey`, and the server refuses to sign unless the env key
  derives exactly that public key.
- Pasting an nsec into the public-key settings field is rejected with an
  explicit error and is never persisted or echoed back. If that happens,
  treat the key as exposed and rotate it.
- The signed event contains only data already on the authenticated proof
  (amounts, member labels, payment hashes, preimages, rule fingerprint) —
  and it is *designed to be public*. **Signing publishes**: once signed, the
  event is best-effort broadcast to the public Nostr relays configured in
  `ORCHESTRATOR_NOSTR_RELAYS` (a small well-known default set unless
  overridden; set it explicitly empty to keep signed proofs local). An event
  accepted by a public relay is permanently public — sign a payment's proof
  only if you are comfortable publishing those details.
- Publishing is never load-bearing: it runs only after the signed event is
  verified and committed, is bounded by a short timeout, and per-relay
  failures are recorded and shown honestly — they can never block signing or
  affect payouts.
- Any code path that would log, serialize, or store `ORCHESTRATOR_NOSTR_SECKEY`
  is in scope for security reports.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |
| < 0.1   | ❌        |

## Reporting a vulnerability

Please report vulnerabilities **privately** via GitHub Security Advisories:
go to the repository's **Security** tab and click **"Report a vulnerability"**.

- Do **not** open a public issue for security problems.
- Include reproduction steps and the affected version/commit.
- There is currently **no bug bounty**; this is a small open-source project.
  You will get an honest response and credit in the fix if you want it.

### In scope

- Authentication bypass or session weaknesses in the dashboard/API
- Payout manipulation (creating, redirecting, inflating, or double-issuing
  payouts beyond what the split rule allows)
- Split-math errors (amounts that don't sum correctly, remainder/dust policy
  violations, rounding exploits)
- Privacy leaks on public proof pages (amounts leaking without opt-in,
  credential or identifier exposure)
- Webhook signature verification flaws (accepting forged BTCPay events)

### Out of scope

- Consequences of running with weak or default database passwords
- Exposing the Postgres port (or other internal services) to the public
  internet
- A compromised host (the operator's machine is the trust root — if the
  attacker has the box, they have everything, by design)
- The plaintext-credentials design fact itself (documented above; hardening it
  is on the roadmap, but reports restating it are not actionable)
- Vulnerabilities in BTCPay Server, LND, or other upstream software (report
  those upstream)
