# OpenSSF Scorecard — Baseline Report

**Team Syntaxerror · Lastprognose-Challenge SoSe26 · captured 2026-06-15**

> This is the **initial baseline** analysis. For the current score, the
> progression (interim **4.1/10**) and the live remediation status, see
> [`openssf-scorecard.md`](./openssf-scorecard.md).

Measured with OpenSSF Scorecard (CLI, `--show-details`) against the live GitHub
repos. Raw data: the `scan_*.txt` files next to this report.

> Purpose: measures the **security / supply-chain maturity** of a repo (not
> forecast accuracy). It connects the course's cybersecurity duty — **EU AI Act
> Art. 15**, code rule **CR-4** (minimal CVE attack surface), **IEC 62443-4-1** —
> to a reproducible 0–10 number.

## 1. Overview

| Repo | Role | Aggregate score |
|---|---|---|
| `linus-thk/syntaxerror-prognose` | **our** forecast tool | **2.1 / 10** |
| `sequential-parameter-optimization/spotforecast2-safe` | certified reference library (course base), as benchmark | 7.7 / 10 |

**Key finding:** our repo starts at **2.1** — expected, and not a verdict on the
code itself. Scorecard rates *open-source release & supply-chain hygiene* (license,
disclosure policy, reviews, signed releases); at baseline ours is a private
forecast-script repo, not a distributed open-source package. The reference library
shows at **7.7** what a mature setup looks like. The gap is less a defect than a
concrete to-do list (§4).

## 2. Our repo `syntaxerror-prognose` — 2.1/10

| Score | Check | Finding |
|---|---|---|
| 10 | Binary-Artifacts | no binaries committed ✅ |
| 9 | Vulnerabilities | 1 known CVE in a dependency (GHSA-rrmf-rvhw-rf47) → fixable |
| 0 | License | no `LICENSE` file |
| 0 | Security-Policy | no `SECURITY.md` |
| 0 | Dependency-Update-Tool | no Dependabot |
| 0 | Branch-Protection | `main` unprotected |
| 0 | Code-Review | 0/30 changesets approved (effectively a single committer) |
| 0 | SAST | no CodeQL etc. |
| 0 | Contributors | 0 organizations detected |
| 0 | CII-Best-Practices | no best-practices badge |
| 0 | Fuzzing | not fuzzed (irrelevant for this project) |
| 0 | Maintained | repo < 90 days → automatic 0 (**structural**, not a real weakness) |
| ? | CI-Tests, Dangerous-Workflow, Packaging, Pinned-Dependencies, Signed-Releases, Token-Permissions | n/a — no CI/releases/tokens to evaluate yet; excluded from the score |

**Reading aids:**
- Only **Binary-Artifacts (10)** and **Vulnerabilities (9)** are positive; the rest
  is 0 or n/a. The many n/a stem from having **no CI/CD pipeline** — nothing to harden.
- **`uv.lock` nuance:** we pin our Python packages exactly (`uv.lock`), which meets
  **CR-4 at the package level**. Scorecard's Pinned-Dependencies inspects
  **CI actions/Dockerfiles**, not `uv.lock` → shown as n/a. Scorecard measures the
  *CI supply-chain layer*, `uv.lock` the *package layer*; **together** they make CR-4.
- **Maintained 0** is an automatic effect for new repos — do not over-read it.

## 3. Benchmark `spotforecast2-safe` — 7.7/10 (what "good" looks like)

| Score | Check | Finding |
|---|---|---|
| 10 | Vulnerabilities · Security-Policy · License · Dependency-Update-Tool · Token-Permissions · Dangerous-Workflow · CI-Tests · Maintained · Packaging · Binary-Artifacts | full hygiene |
| 9 | Pinned-Dependencies | all 41 CI actions pinned by hash; only 1 npm command open |
| 8 | SAST | CodeQL (17/25 commits) |
| 8 | Signed-Releases | 5/5 releases signed via **Sigstore**, incl. a **`sbom.cdx.json`** (signed SBOM!); only SLSA provenance missing |
| 6 | Contributors | 2 organizations |
| 5 | CII-Best-Practices | "Passing" badge |
| 1 | Branch-Protection | `develop` unprotected; `main` only partial |
| 0 | Code-Review · Fuzzing | 0/15 approved changesets; no fuzzing |

**Mapping highlight:** the certified library even signs its releases as an **SBOM**
(`sbom.cdx.json` via Sigstore) — chapter 11 (provenance) + AI Act Art. 11/12 made
tangible. Even it reaches only 7.7 → a good score is work, not automatic.

## 4. Mapping Scorecard check → course concept (the core of the report)

| Scorecard check | Course concept | AI Act / standard |
|---|---|---|
| Pinned-Dependencies | **CR-4** (attack surface) + **CR-2** (determinism) | Art. 15 |
| Vulnerabilities, Dependency-Update-Tool | **CR-4** (minimal CVE surface, deps current) | Art. 15 |
| SAST, Dangerous-Workflow, Token-Permissions | cybersecurity of the pipeline itself | Art. 15 / IEC 62443-4-1 |
| Branch-Protection, Code-Review | **CR-1** (everything reviewed) + auditability | Art. 12 |
| Signed-Releases, SBOM | provenance / integrity (ch. 11) | Art. 11, 12 / SLSA |
| Security-Policy | secure development lifecycle | IEC 62443-4-1 |

## 5. Remediation (prioritized, cheapest first)

One-time setups that do not disturb the modelling work (repo owner implements):
1. Add `LICENSE` → License 0→10.
2. Add `SECURITY.md` → Security-Policy 0→10.
3. Enable Dependabot (`.github/dependabot.yml`) → Dependency-Update-Tool 0→10.
4. Fix the known CVE → Vulnerabilities 9→10.
5. Branch protection on `main` (PR + 1 approval) → Branch-Protection + enables Code-Review.
6. Mutual PR "approve" (ongoing habit) → Code-Review.
7. (optional) CodeQL → SAST; a minimal CI test → CI-Tests.

> **Status update:** items 1–3 are **already done** (reflected in the interim
> 4.1 score) — see [`openssf-scorecard.md`](./openssf-scorecard.md) for the live state.

## 6. Methodology / reproducibility

- Tool: OpenSSF Scorecard (CLI), auth via `gh auth token`.
- Command per repo: `scorecard --repo=github.com/<owner>/<repo> --show-details`.
- Aggregate = risk-weighted mean of the checks that ran (Critical 10, High 7.5,
  Medium 5, Low 5; n/a / errored checks excluded).
- Measured: our repo + the reference library (benchmark).
- Planned: **final re-score** before the closing presentation → before/after.
