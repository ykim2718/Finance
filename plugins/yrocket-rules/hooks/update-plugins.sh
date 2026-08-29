#!/usr/bin/env bash
__version__="0.1.1.2026.8.29"  # Semantic Versioning: Major.Minor.Patch.Date(YYYY.M.D)
# Update the marketplace and every installed plugin at session start.
{
  command -v claude >/dev/null 2>&1 || { echo "claude CLI not found; skipping plugin self-update"; exit 0; }
  state="$HOME/.claude/plugins/installed_plugins.json"
  [ -f "$state" ] || { echo "no installed plugins"; exit 0; }
  date "+=== session start %Y-%m-%d %H:%M:%S"
  claude plugin marketplace update
  for p in $(grep -oE '"[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+"' "$state" | tr -d '"' | sort -u); do
    claude plugin update "$p"
  done
} >> "$HOME/.claude/plugin-autoupdate.log" 2>&1
