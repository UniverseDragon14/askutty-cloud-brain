#!/bin/bash
OUT="$HOME/askutty-notes/TOOLS_INVENTORY_$(date +%Y%m%d_%H%M).md"

{
echo "# ASKUTTY Tools Inventory"
echo "Date: $(date)"
echo
echo "## Device"
hostname
whoami
hostname -I
df -h /
echo
echo "## CLI Tools"
for c in git gh gcloud gemini python3 node npm cloudflared tmate ssh rsync nmap ffmpeg; do
  if command -v $c >/dev/null 2>&1; then
    echo "- $c: FOUND ($(command -v $c))"
  else
    echo "- $c: MISSING"
  fi
done
echo
echo "## Auth Status"
echo "### GitHub"
gh auth status 2>&1 | sed 's/oauth_token.*/oauth_token: REDACTED/g'
echo
echo "### Google Cloud"
gcloud auth list 2>/dev/null
gcloud config get-value project 2>/dev/null
gcloud billing projects describe "$(gcloud config get-value project 2>/dev/null)" 2>/dev/null | grep -E "billingEnabled|billingAccountName|projectId" || true
echo
echo "## Secret Env Presence Only"
for v in OPENAI_API_KEY GEMINI_API_KEY GOOGLE_API_KEY GROQ_API_KEY GITHUB_TOKEN CLOUDFLARE_TOKEN ASKUTTY_TOKEN; do
  if [ -n "${!v}" ]; then
    echo "- $v: SET"
  else
    echo "- $v: NOT SET"
  fi
done
echo
echo "## Notes"
echo "- Do not save OTP codes."
echo "- Do not save private keys."
echo "- Do not paste API keys in chat."
echo "- Store only provider name + purpose + where saved."
} > "$OUT"

echo "$OUT"
cat "$OUT"
