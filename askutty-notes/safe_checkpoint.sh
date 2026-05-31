#!/bin/bash
set -e
tar -czf ~/askutty-checkpoints/askutty-safe_$(date +%Y%m%d_%H%M).tar.gz \
  --exclude='*/.venv' \
  --exclude='*/__pycache__' \
  --exclude='*.pyc' \
  ~/askutty-pi5 ~/askutty-notes
echo "ASKUTTY safe checkpoint created ✅"
