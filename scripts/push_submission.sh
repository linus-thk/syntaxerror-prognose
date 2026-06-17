#!/bin/bash

# Script zum automatischen Pushen von Submission-CSVs mit PR ins challenge-leaderboard
# Erfordert: git, gh (GitHub CLI)

set -e

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Funktionen
print_error() {
    echo -e "${RED}✗ $1${NC}" >&2
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Pfade
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SOURCE_SUBMISSION_DIR="$PROJECT_ROOT/submissions/syntaxerror"

# Finde challenge-leaderboard Repo (Geschwister-Repo neben syntaxerror-prognose)
PARENT_DIR="$(dirname "$PROJECT_ROOT")"
LEADERBOARD_DIR="$PARENT_DIR/challenge-leaderboard"
TARGET_SUBMISSION_DIR="$LEADERBOARD_DIR/submissions/syntaxerror"

if [ ! -d "$LEADERBOARD_DIR" ]; then
    print_error "challenge-leaderboard Repo nicht gefunden: $LEADERBOARD_DIR"
    echo "Stellt sicher, dass das Repo neben syntaxerror-prognose geklont ist."
    exit 1
fi

print_success "challenge-leaderboard gefunden: $LEADERBOARD_DIR"

# Datum berechnen (Morgen)
# macOS: date -u -v+1d +"%Y-%m-%d"
# Linux: date -u -d "+1 day" +"%Y-%m-%d"
FORECAST_DATE=$(date -u -v+1d +"%Y-%m-%d" 2>/dev/null || date -u -d "+1 day" +"%Y-%m-%d")

print_info "Forecast-Datum: $FORECAST_DATE"

# CSV-Datei finden
SOURCE_CSV_FILE="$SOURCE_SUBMISSION_DIR/$FORECAST_DATE.csv"

if [ ! -f "$SOURCE_CSV_FILE" ]; then
    print_error "CSV-Datei nicht gefunden: $SOURCE_CSV_FILE"
    echo "Verfügbare Dateien in $SOURCE_SUBMISSION_DIR:"
    ls -la "$SOURCE_SUBMISSION_DIR" || true
    exit 1
fi

print_success "CSV-Datei gefunden: $(basename $SOURCE_CSV_FILE)"

# CSV ins challenge-leaderboard Repo kopieren
TARGET_CSV_FILE="$TARGET_SUBMISSION_DIR/$FORECAST_DATE.csv"
mkdir -p "$TARGET_SUBMISSION_DIR"

print_info "Kopiere CSV zu: $TARGET_CSV_FILE"
cp "$SOURCE_CSV_FILE" "$TARGET_CSV_FILE"
print_success "CSV kopiert"

# Branch-Name und Summary
BRANCH_NAME="submission/syntaxerror/$FORECAST_DATE"
SUMMARY="submission(syntaxerror): forecast $FORECAST_DATE"

print_info "Branch: $BRANCH_NAME"
print_info "Summary: $SUMMARY"

# Ins challenge-leaderboard Repo gehen
cd "$LEADERBOARD_DIR"

# Upstream Remote hinzufügen, falls nicht vorhanden
if ! git remote get-url upstream >/dev/null 2>&1; then
    print_info "Füge upstream Remote hinzu..."
    git remote add upstream https://github.com/bartzbeielstein/challenge-leaderboard.git
fi

# main mit upstream synchronisieren, damit der neue Branch garantiert nur die
# aktuelle CSV enthält (sonst werden CSVs aus alten, noch ausgecheckten
# Submission-Branches mit übernommen)
print_info "Synchronisiere main mit upstream..."
git fetch upstream main
git checkout main
git reset --hard upstream/main

# Branch immer frisch von main erstellen (alten lokalen Branch ggf. verwerfen)
if git rev-parse --verify "$BRANCH_NAME" >/dev/null 2>&1; then
    print_info "Verwerfe alten lokalen Branch: $BRANCH_NAME"
    git branch -D "$BRANCH_NAME"
fi
print_info "Erstelle neuen Branch: $BRANCH_NAME"
git checkout -b "$BRANCH_NAME"

# Änderungen hinzufügen und commiten
print_info "Staging: $(basename $TARGET_CSV_FILE)"
git add "$TARGET_CSV_FILE"

if git diff --cached --quiet; then
    print_info "Keine neuen Änderungen zu committen"
else
    print_info "Committing..."
    git commit -m "$SUMMARY"
    print_success "Commit erstellt"
fi

# Pushen zu Fork (origin) - force, da der Branch oben ggf. neu von main erstellt wurde
print_info "Pushe zu origin/$BRANCH_NAME"
git push -f -u origin "$BRANCH_NAME"
print_success "Gepusht"

# PR gegen upstream erstellen
print_info "Erstelle PR gegen bartzbeielstein/challenge-leaderboard..."

# GitHub-Username auslesen
GITHUB_USER=$(gh api user -q .login 2>/dev/null || echo "")
if [ -z "$GITHUB_USER" ]; then
    print_error "Kann GitHub-Username nicht auslesen. Stelle sicher, dass du mit 'gh auth login' authentifiziert bist."
    exit 1
fi

if gh pr create \
    --repo bartzbeielstein/challenge-leaderboard \
    --title "$SUMMARY" \
    --body "Automatisch generierte Submission für $FORECAST_DATE" \
    --base main \
    --head "$GITHUB_USER:$BRANCH_NAME" 2>&1 | grep -q "already exists"; then
    print_info "PR existiert bereits"
else
    print_success "PR erstellt"
fi

print_success "🚀 Fertig!"
