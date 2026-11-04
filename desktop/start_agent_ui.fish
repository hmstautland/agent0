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
# Not silenced: if HTTPS isn't enabled on the tailnet yet, serve prints an
# enable link and waits for it.
if command -q tailscale
    if not tailscale serve --bg 8000
        echo "tailscale serve failed - the UI is only reachable at http://127.0.0.1:8000"
    end
end

# With the on-demand systemd units installed (README "Remote access over
# Tailscale") the socket owns port 8000: start the app through it and show its
# logs instead of running a second uvicorn.
if systemctl --user -q is-active agent0-ui-proxy.socket
    curl -s -o /dev/null http://127.0.0.1:8000/login
    echo "Agent 0 is running at http://127.0.0.1:8000 (Ctrl+C closes the logs, not the app)"
    exec journalctl --user -u agent0-ui -f
end

uvicorn core.ui:app --host 127.0.0.1 --port 8000
