#!/usr/bin/env fish
# UI Launcher - CachyOS / fish

set -l script_dir (dirname (status --current-filename))
set -l project_root (realpath $script_dir/..)

cd $project_root

source venv/bin/activate.fish

if not curl -s -o /dev/null http://localhost:11434
    echo "Starting ollama..."
    ollama serve &
    sleep 1
end

# Reach the UI from other devices through Tailscale: `tailscale serve` proxies
# https://<machine>.<tailnet>.ts.net to the local port, so uvicorn only listens
# on localhost and the app is never exposed on the LAN. HTTPS also matters for
# the mic button - browsers only allow getUserMedia on a secure origin.
if command -q tailscale
    if tailscale serve --bg 8000 >/dev/null
        tailscale serve status
    else
        echo "tailscale serve failed - the UI is only reachable at http://127.0.0.1:8000"
    end
end

uvicorn core.ui:app --host 127.0.0.1 --port 8000
