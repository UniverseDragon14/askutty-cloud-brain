#!/bin/bash
set -e

SRC_NOTES="$HOME/askutty-notes"
SRC_PI5="$HOME/askutty-pi5"
DEST="$HOME/askutty-cloud-brain"

echo "[ASKUTTY] Syncing notes and Pi5 brain..."

rsync -a --delete \
  --exclude='.env' \
  --exclude='*.key' \
  --exclude='*.pem' \
  --exclude='*.log' \
  "$SRC_NOTES/" "$DEST/askutty-notes/"

rsync -a --delete \
  --exclude='.env' \
  --exclude='*.key' \
  --exclude='*.pem' \
  --exclude='*.log' \
  --exclude='__pycache__/' \
  "$SRC_PI5/" "$DEST/askutty-pi5/"

cd "$DEST"

git add .
if git diff --cached --quiet; then
  echo "[ASKUTTY] No changes to backup."
  exit 0
fi

git commit -m "ASKUTTY auto backup $(date '+%Y-%m-%d %H:%M')"
git push

echo "[ASKUTTY] Backup pushed to GitHub ✅"
