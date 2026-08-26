#!/bin/bash
set -e

# Change to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "      JarvisBot Update & Deploy         "
echo "========================================"

# 1. Fetch latest changes from remote main
echo "Fetching origin/main..."
git fetch origin main

# 2. Check if there are new commits
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "Bot is already up to date with origin/main (${LOCAL:0:7})."
    # If interactive terminal, ask if user wants to force restart
    if [ -t 0 ]; then
        read -p "Force restart service anyway? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Restarting service..."
            sudo systemctl restart jarvisbot
            echo "Service restarted."
        fi
    fi
    exit 0
fi

# 3. Check if requirements.txt changed between HEAD and origin/main
REQ_CHANGED=false
if git diff --name-only HEAD origin/main | grep -q "^requirements.txt$"; then
    REQ_CHANGED=true
fi

# 4. Pull latest changes
echo "Pulling updates from main..."
git pull origin main

# 5. Update venv if requirements.txt changed
if [ "$REQ_CHANGED" = true ]; then
    echo "Detected changes in requirements.txt. Updating virtual environment dependencies..."
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
    echo "Dependencies successfully updated."
else
    echo "No changes in requirements.txt. Skipping pip install."
fi

# 6. Restart systemd service
echo "Restarting jarvisbot systemd service..."
sudo systemctl restart jarvisbot

# 7. Verify service status
sleep 1
if sudo systemctl is-active --quiet jarvisbot; then
    echo "JarvisBot is running successfully! (Commit: $(git rev-parse --short HEAD))"
else
    echo "Warning: JarvisBot failed to start. Check logs with: journalctl -u jarvisbot -e"
    exit 1
fi
