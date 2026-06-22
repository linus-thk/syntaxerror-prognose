# OpenSSF Scorecard — Security Posture

**Team Syntaxerror · Lastprognose-Challenge SoSe26**

[OpenSSF Scorecard](https://scorecard.dev/) is an automated tool that rates a
GitHub repository's security posture from **0 to 10** across ~18 best-practice
checks (license, security policy, code review, dependency hygiene, static
analysis, signed releases, …). We track it because it turns the course's
cybersecurity duty into a reproducible number: **EU AI Act Art. 15**, code rule
**CR-4** (minimal CVE attack surface), and **IEC 62443-4-1**.

This document records our **baseline**, the **remediation roadmap**, and the
**re-scoring plan**. Raw scan output lives alongside it
(`scan_syntaxerror.txt`, `scan_spotforecast2safe.txt`).

---

## Baseline score: **2.1 / 10**  · captured 2026-06-15

A low starting value is expected for a young forecasting repository: Scorecard
measures **open-source release hygiene** (license, disclosure policy, reviews,
signed releases) — **not** forecast quality.

**Benchmark.** We measure ourselves against the upstream certified library
[`spotforecast2-safe`](https://github.com/sequential-parameter-optimization/spotforecast2-safe)
at **7.7 / 10** — a strong reference for the practices we are adopting (signed
SBOM releases, Dependabot, CodeQL, pinned CI actions, a security policy).

| Status | Check | Score |
|:--|:--|:--:|
| ✅ pass | Binary-Artifacts (no binaries committed) | 10 |
| ✅ near | Vulnerabilities (1 known CVE still open) | 9 |
| ❌ missing | **License** | 0 |
| ❌ missing | **Security-Policy** (`SECURITY.md`) | 0 |
| ❌ missing | **Dependency-Update-Tool** (Dependabot) | 0 |
| ❌ missing | **Branch-Protection** | 0 |
| ❌ missing | **Code-Review** | 0 |
| ❌ missing | **SAST** (static analysis) | 0 |
| ❌ missing | CII-Best-Practices · Contributors · Fuzzing | 0 |
| ⚠️ automatic | Maintained (repo < 90 days → auto-0, not a real weakness) | 0 |
| ⚪ n/a | CI-Tests · Dangerous-Workflow · Packaging · Pinned-Dependencies · Signed-Releases · Token-Permissions (no CI/releases yet) | – |

> **Note on Pinned-Dependencies (n/a):** this does not mean we don't pin — our
> Python dependencies are exactly pinned via `uv.lock` (CR-4 at the package
> level). Scorecard's check only inspects the CI/Actions layer.

---

## Remediation roadmap

### Implemented since baseline
- **`LICENSE`** added → License **0 → 10**
- **Dependabot** (`.github/dependabot.yml`) → Dependency-Update-Tool **0 → 10**

### Open (targeted before challenge end)
- **`SECURITY.md`** (disclosure/contact process) → Security-Policy
- **CodeQL / CI workflow** → SAST + CI-Tests
- **Patch known vulnerability** `GHSA-rrmf-rvhw-rf47` → Vulnerabilities **9 → 10**
- **Branch protection** on `main` + mutual **PR reviews** → Branch-Protection + Code-Review

---

## Re-scoring plan

We treat **2.1 / 10** as a deliberate **baseline**. A **final re-score** at the
**challenge end (2026-07-20)** will document the security improvement as a
clear before/after — OpenSSF Scorecard is a **graded** challenge component.

## Reproduce

```sh
# requires the OpenSSF Scorecard CLI (`brew install scorecard`) and a GitHub token
GITHUB_AUTH_TOKEN="$(gh auth token)" \
  scorecard --repo=github.com/linus-thk/syntaxerror-prognose --show-details
```
