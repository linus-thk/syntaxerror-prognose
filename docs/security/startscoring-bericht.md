# OpenSSF Scorecard — Startscoring-Bericht (Baseline)

**Team Syntaxerror · Lastprognose-Challenge SoSe26 · Stand: 2026-06-15**
Erhoben mit OpenSSF Scorecard (CLI, `--show-details`) gegen die Live-Repos auf
GitHub. Rohdaten: die `scan_*.txt`-Dateien neben diesem Bericht.

> Zweck: misst die **Sicherheits-/Lieferketten-Reife** eines Repos (nicht die
> Forecast-Genauigkeit). Bindet die Cybersecurity-Pflicht des Kurses — **KI-VO
> Art. 15**, Code-Regel **CR-4** (minimale CVE-Angriffsfläche), **IEC 62443-4-1**
> — an eine reproduzierbare Zahl 0–10.

## 1. Übersicht

| Repo | Rolle | Aggregate Score |
|---|---|---|
| `linus-thk/syntaxerror-prognose` | **unser** Forecast-Tool | **2.1 / 10** |
| `sequential-parameter-optimization/spotforecast2-safe` | zertifizierte Referenz-Bibliothek (Kurs-Basis), als Benchmark | 7.7 / 10 |

**Kernbefund:** Unser Repo startet bei **2.1**. Das ist **erwartbar und kein
schlechtes Zeichen über den Code selbst** — Scorecard bewertet *OSS-Veröffentlichungs-
und Lieferketten-Hygiene* (Lizenz, Melde-Policy, Reviews, CI-Härtung), und unser
Repo ist (bisher) ein **privates Forecast-Skript-Repo**, kein verteiltes
Open-Source-Paket. Die Referenz-Bibliothek zeigt mit **7.7**, wie das „fertig"
aussieht. Der Abstand ist also weniger ein Mangel als eine **konkrete To-do-Liste**
(§4) — und genau das macht den Bericht für die Präsentation wertvoll.

## 2. Unser Repo `syntaxerror-prognose` — 2.1/10

| Score | Check | Befund |
|---|---|---|
| 10 | Binary-Artifacts | keine Binärdateien im Repo ✅ |
| 9 | Vulnerabilities | **1 bekannte Schwachstelle** in einer Abhängigkeit (GHSA-rrmf-rvhw-rf47) → behebbar |
| 0 | License | keine `LICENSE`-Datei |
| 0 | Security-Policy | keine `SECURITY.md` |
| 0 | Dependency-Update-Tool | kein Dependabot |
| 0 | Branch-Protection | `main` ungeschützt |
| 0 | Code-Review | 0/30 Changesets approved (faktisch ein Committer) |
| 0 | SAST | kein CodeQL o. Ä. |
| 0 | Contributors | 0 Organisationen erkannt |
| 0 | CII-Best-Practices | kein Best-Practices-Badge |
| 0 | Fuzzing | kein Fuzzing (für dieses Projekt irrelevant) |
| 0 | Maintained | Repo **< 90 Tage alt** → automatischer 0er (**strukturell**, keine echte Schwäche) |
| ? | CI-Tests, Dangerous-Workflow, Packaging, Pinned-Dependencies, Signed-Releases, Token-Permissions | „n/a" — es gibt (noch) keine GitHub-Actions/Releases/Tokens zum Prüfen; zählen **nicht** in den Score |

**Lesehilfen für die Präsentation:**
- Nur **Binary-Artifacts (10)** und **Vulnerabilities (9)** sind positiv; der Rest
  ist 0 oder „n/a". Die vielen „n/a" kommen daher, dass das Repo **keine CI/CD-Pipeline**
  hat — es gibt schlicht nichts zu härten.
- **`uv.lock`-Nuance:** Wir pinnen unsere Python-Pakete exakt (`uv.lock`) — das
  erfüllt **CR-4 auf Paket-Ebene** vorbildlich. Scorecards „Pinned-Dependencies"
  schaut aber auf **CI-Actions/Dockerfiles**, nicht auf `uv.lock` → erscheint hier
  als „n/a". Wichtige Aussage: Scorecard misst die *Lieferketten-Ebene der CI*,
  `uv.lock` die *Paket-Ebene*; **beide zusammen** ergeben CR-4.
- **Maintained 0** ist ein Automatismus für neue Repos, nicht überbewerten.

## 3. Benchmark `spotforecast2-safe` — 7.7/10 (so sieht „gut" aus)

| Score | Check | Befund |
|---|---|---|
| 10 | Vulnerabilities · Security-Policy · License · Dependency-Update-Tool · Token-Permissions · Dangerous-Workflow · CI-Tests · Maintained · Packaging · Binary-Artifacts | volle Hygiene |
| 9 | Pinned-Dependencies | alle 41 CI-Actions per Hash gepinnt; nur 1 npm-Befehl offen |
| 8 | SAST | CodeQL (17/25 Commits) |
| 8 | Signed-Releases | 5/5 Releases per **Sigstore** signiert, inkl. **`sbom.cdx.json`** (signierte SBOM!); fehlt nur SLSA-Provenance |
| 6 | Contributors | 2 Organisationen |
| 5 | CII-Best-Practices | „Passing"-Badge |
| 1 | Branch-Protection | `develop` ungeschützt; `main` nur teils |
| 0 | Code-Review · Fuzzing | 0/15 approved Changesets; kein Fuzzing |

**Pointe fürs Mapping:** Die zertifizierte Bibliothek signiert ihre Releases sogar
als **SBOM** (`sbom.cdx.json` via Sigstore) — das ist Kapitel 11 (Provenienz) +
KI-VO Art. 11/12 zum Anfassen. Selbst sie erreicht nur 7.7 (Code-Review/Fuzzing 0)
→ ein guter Score ist Arbeit, kein Automatismus.

## 4. Übersetzung Scorecard-Check → Kurs-Konzept (Kern des Berichts)

| Scorecard-Check | Kurs-Konzept | KI-VO / Norm |
|---|---|---|
| Pinned-Dependencies | **CR-4** (Angriffsfläche) + **CR-2** (Determinismus) | Art. 15 |
| Vulnerabilities, Dependency-Update-Tool | **CR-4** (minimale CVE-Fläche, Deps aktuell) | Art. 15 |
| SAST, Dangerous-Workflow, Token-Permissions | Cybersecurity der Pipeline selbst | Art. 15 / IEC 62443-4-1 |
| Branch-Protection, Code-Review | **CR-1** (alles geprüft) + Auditierbarkeit | Art. 12 |
| Signed-Releases, SBOM | Provenienz/Integrität (Kap. 11) | Art. 11, 12 / SLSA |
| Security-Policy | Secure Development Lifecycle | IEC 62443-4-1 |

## 5. Maßnahmen, um unseren Score zu heben (priorisiert, billig zuerst)

Einmal-Setups, die die Modellarbeit **nicht** stören (Repo-Owner Linus setzt um;
die Dateien kann ich vorbereiten):

1. **`LICENSE`** hinzufügen → License 0→10.
2. **`SECURITY.md`** (kurze Melde-Anleitung) → Security-Policy 0→10.
3. **Dependabot** anschalten (`.github/dependabot.yml`) → Dependency-Update-Tool 0→10 (hilft auch, die 1 Schwachstelle zu schließen).
4. **Die 1 bekannte Schwachstelle beheben** (gemeldete Abhängigkeit aktualisieren) → Vulnerabilities 9→10.
5. **Branch-Protection** auf `main` (PR + 1 Approval) → Branch-Protection rauf **und** ermöglicht Code-Review-Punkte.
6. **PRs gegenseitig „approven"** (laufende Gewohnheit) → Code-Review.
7. (optional, mehr Aufwand) minimaler CI-Test-Workflow → CI-Tests; CodeQL → SAST; OpenSSF-Best-Practices-Badge → CII.

> Hinweis: Maßnahmen 5+6 = der zuvor geparkte „Pull-Request"-Punkt — hier als
> konkrete Score-Hebel. Mit nur 1–3 (drei Dateien) käme das Repo grob von **2.1**
> auf den mittleren Bereich; mit 5+6 weiter rauf.

## 6. Methodik / Reproduzierbarkeit

- Tool: OpenSSF Scorecard (CLI), Auth via `gh auth token`.
- Befehl je Repo: `scorecard --repo=github.com/<owner>/<repo> --show-details`.
- Aggregat = risiko-gewichteter Mittel der durchgelaufenen Checks (Critical 10,
  High 7.5, Medium 5, Low 5; „?"/n/a-Checks ausgenommen).
- Gemessen: unser Repo + die Referenz-Bibliothek (Benchmark).
- Geplant: **Schlussmessung** vor der Abschlusspräsentation → Vorher/Nachher.
