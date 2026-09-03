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

uvicorn core.ui:app --host 0.0.0.0 --port 8000