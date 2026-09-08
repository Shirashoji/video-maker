#!/bin/sh
set -eu
plugin_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PATH="$PATH:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin"
export PATH
if ! command -v uv >/dev/null 2>&1; then
    echo 'Video Maker requires uv. Install uv, then restart this plugin.' >&2
    exit 1
fi
# Runtime and media live outside the versioned plugin cache, surviving reinstall.
runtime_dir="${VIDEO_MAKER_RUNTIME:-$HOME/Library/Caches/video-maker}"
export UV_PROJECT_ENVIRONMENT="$runtime_dir/venv"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$runtime_dir/uv-cache}"
export PYTHONPATH="$plugin_dir/src${PYTHONPATH:+:$PYTHONPATH}"
workspace_dir="${VIDEO_MAKER_WORKSPACE:-$HOME/Movies/VideoMaker}"
exec uv run --directory "$plugin_dir" --frozen --no-dev python -m video_maker.server --workspace "$workspace_dir"
