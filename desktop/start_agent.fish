#!/usr/bin/env fish
# Shortcut terminal (CLI agent) - CachyOS / fish

set -l script_dir (dirname (status --current-filename))
set -l project_root (realpath $script_dir/..)

cd $project_root

source venv/bin/activate.fish

if not curl -s -o /dev/null http://localhost:11434
    echo "Starting ollama..."
    ollama serve &
    sleep 1
end

python -m agent
