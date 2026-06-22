# OpenSSF Scorecard — Security Posture

**Team Syntaxerror · Lastprognose-Challenge SoSe26**

[OpenSSF Scorecard](https://scorecard.dev/) rates a GitHub repository's security
posture from **0 to 10** across ~18 best-practice checks. We track it because it
turns the course's cybersecurity duty into a reproducible number: **EU AI Act
Art. 15**, code rule **CR-4** (minimal CVE attack surface), and **IEC 62443-4-1**.

## Score progression

| Stage | Score | Date |
|:--|:--:|:--|
| Baseline (initial scan) | 2.1 / 10 | 2026-06-15 |
| **Current — interim** | **4.1 / 10** | 2026-06-22 |
| Final re-score (challenge end) | _planned_ | by 2026-07-20 |

> **The current 4.1 is an interim checkpoint, not the final result** — several
> checks are still open (see below). Benchmark: the upstream certified library
> [`spotforecast2-safe`](https://github.com/sequential-parameter-optimization/spotforecast2-safe)
> scores **7.7 / 10**, a strong reference for the practices we are adopting.

A low score is expected for a young forecasting repo: Scorecard measures
**open-source release hygiene** (license, disclosure policy, reviews, dependency
hygiene) — **not** forecast quality.

## Current check status (4.1 / 10)

| Status | Check | Score |
|:--|:--|:--:|
| ✅ pass | License | 10 |
| ✅ pass | Security-Policy (`.github/SECURITY.md`) | 10 |
| ✅ pass | Dependency-Update-Tool (Dependabot) | 10 |
| ✅ pass | Binary-Artifacts (no binaries committed) | 10 |
| ◐ partial | Vulnerabilities — **3 known CVEs** in dependencies | 7 |
| ❌ open | Branch-Protection | 0 |
| ❌ open | Code-Review | 0 |
| ❌ open | SAST (static analysis) | 0 |
| ❌ open | CII-Best-Practices · Contributors · Fuzzing | 0 |
| ⚠️ auto | Maintained (repo < 90 days → automatic 0, resolves with age) | 0 |
| ⚪ n/a | CI-Tests · Dangerous-Workflow · Packaging · Pinned-Dependencies · Signed-Releases · Token-Permissions | – |

> Note: `uv.lock` pins our Python dependencies exactly (CR-4 at the package
> level); Scorecard's Pinned-Dependencies check only inspects the CI/Actions
> layer, hence n/a here.

## Why 4.1 — and not higher

The aggregate is a **risk-weighted average** of the applicable checks, not a sum
of points. Two effects hold it at 4.1:

1. **The remaining zeros carry the highest weight.** Branch-Protection,
   Code-Review and Maintained are all *high*-risk checks still at 0 and pull the
   mean down hard; three new passing checks lift the average only partially.
2. **Vulnerabilities slipped 9 → 7.** New dependencies introduced **3 known
   CVEs** (was 1) — a high-weighted check losing ground offsets part of the gain.
   A textbook **CR-4** reminder that every dependency is attack surface.

## Remediation

**✅ Done since baseline (reflected in 4.1):**
- `LICENSE` → License **0 → 10**
- `.github/SECURITY.md` → Security-Policy **0 → 10**
- Dependabot (`.github/dependabot.yml`) → Dependency-Update-Tool **0 → 10**

**🔧 Open (targeted before challenge end):**
- Resolve the **3 known CVEs** (Dependabot will propose the updates) → Vulnerabilities → 10
- **Branch protection** on `main` + mutual **PR reviews** → Branch-Protection + Code-Review
- **CodeQL / CI workflow** → SAST + CI-Tests
- Maintained clears automatically once the repo passes 90 days

## Final scoring

We treat the numbers as **baseline (2.1) → interim (4.1) → final**. A **final
re-score at challenge end (2026-07-20)** documents the full before/after —
OpenSSF Scorecard is a **graded** challenge component.

## Reproduce

```sh
# requires the OpenSSF Scorecard CLI (`brew install scorecard`) and a GitHub token
GITHUB_AUTH_TOKEN="$(gh auth token)" \
  scorecard --repo=github.com/linus-thk/syntaxerror-prognose --show-details
```
