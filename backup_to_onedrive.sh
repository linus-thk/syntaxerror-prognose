#!/bin/bash

# Script zum Backup des syntaxerror-prognose Repos als ZIP
# Speichert im OneDrive-Ordner mit Datum

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
BACKUP_DIR="/Users/linuswolff/Library/CloudStorage/OneDrive-Persönlich/09_Studium/MAN/Backup_History"
REPO_NAME="syntaxerror-prognose"

# Datum
BACKUP_DATE=$(date +"%Y-%m-%d_%H-%M-%S")
ZIP_FILE="$BACKUP_DIR/${REPO_NAME}_${BACKUP_DATE}.zip"

# Backup-Verzeichnis prüfen
if [ ! -d "$BACKUP_DIR" ]; then
    print_error "Backup-Verzeichnis nicht gefunden: $BACKUP_DIR"
    exit 1
fi

print_success "Backup-Verzeichnis: $BACKUP_DIR"

# ZIP erstellen (mit Ausnahmen)
print_info "Erstelle ZIP-Backup: $(basename $ZIP_FILE)"

cd "$SCRIPT_DIR"

# Zip mit Ausnahmen (venv, .git, __pycache__, .pytest_cache, etc.)
zip -r "$ZIP_FILE" . \
    -x \
    ".venv/*" \
    ".git/*" \
    "__pycache__/*" \
    ".pytest_cache/*" \
    "*.pyc" \
    ".DS_Store" \
    "build_zip.sh" \
    > /dev/null 2>&1

if [ $? -eq 0 ]; then
    print_success "ZIP erstellt: $(basename $ZIP_FILE)"
    
    # Dateigröße anzeigen
    SIZE=$(du -h "$ZIP_FILE" | cut -f1)
    print_success "Größe: $SIZE"
else
    print_error "Fehler beim ZIP-Erstellen"
    exit 1
fi

print_success "🚀 Backup gespeichert!"
