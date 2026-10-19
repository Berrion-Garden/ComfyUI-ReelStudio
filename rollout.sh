#!/usr/bin/env bash
# Rollout: build the UI, ship web/dist, restart ComfyUI only when backend
# python changed, then verify the deployed endpoint — including the public
# one. Wiring is env-driven from the repo-root .env (variable owner:
# .env.example); the deployment story: docs/deployment.md.
# Referenced from AGENTS.md as the only supported way to land changes.
set -euo pipefail
cd "$(dirname "$0")"

# env: real environment > .env at the repo root (REELSTUDIO_ENV relocates it)
ENV_FILE=${REELSTUDIO_ENV:-.env}
if [ -f "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi

SERVICE=${REELSTUDIO_COMFYUI_SERVICE:-comfyui.service}
BASE_URL=${REELSTUDIO_LOCAL_URL:-http://127.0.0.1:8188}
APP_URL="$BASE_URL/reelstudio"
PUBLIC_URL=${REELSTUDIO_PUBLIC_URL:-}

step() { printf '\n== %s\n' "$*"; }

step "build the UI"
(cd frontend && npm run build)
rm -rf web/dist/assets
cp -r frontend/dist/* web/dist/

step "did backend python change since the service started?"
# web/dist is served from disk, so a frontend-only rollout needs no restart —
# but python lives in the running process, and a stale module means the OLD
# handlers keep answering no matter what the browser refreshes
svc_ts=0
ts_str=$(systemctl --user show -p ActiveEnterTimestamp --value "$SERVICE" 2>/dev/null || true)
if [ -n "$ts_str" ]; then svc_ts=$(date -d "$ts_str" +%s 2>/dev/null) || svc_ts=0; fi
py_ts=$(find reelstudio __init__.py -name '*.py' -printf '%T@\n' 2>/dev/null \
  | sort -n | tail -1 | cut -d. -f1)
if [ "$py_ts" -gt "$svc_ts" ] 2>/dev/null; then
  step "backend is stale — drain the queue, restart $SERVICE"
  until curl -sf -m 5 "$BASE_URL/queue" | grep -q '"queue_running": \[\]'; do
    echo "   jobs running — waiting for an empty queue (Ctrl-C to abort)"
    sleep 5
  done
  systemctl --user restart "$SERVICE"
else
  step "backend is current — no restart needed"
fi

step "wait for the app to answer"
up=0
for _ in $(seq 1 60); do
  if curl -sf -m 5 "$APP_URL/api/project" >/dev/null; then up=1; break; fi
  sleep 2
done
[ "$up" = 1 ] || { echo "app did not come up at $APP_URL"; exit 1; }

step "verify"
bundle=$(curl -sf "$APP_URL/" | grep -o 'index-[^"]*\.js' | head -1)
if [ -n "$bundle" ] && [ -f "web/dist/assets/$bundle" ]; then
  echo "local  $APP_URL serves the fresh bundle: $bundle"
else
  echo "local endpoint does not serve the fresh build"; exit 1
fi

if [ -n "$PUBLIC_URL" ]; then
  pub_bundle=$(curl -sf -m 10 "$PUBLIC_URL" | grep -o 'index-[^"]*\.js' | head -1)
  if [ "$pub_bundle" != "$bundle" ]; then
    echo "public endpoint serves $pub_bundle, expected $bundle"; exit 1
  fi
  echo "public $PUBLIC_URL serves the same bundle"
  curl -sf -m 10 "$PUBLIC_URL/api/project" >/dev/null \
    && echo "public API answers" \
    || { echo "public API broken"; exit 1; }
fi

step "rolled out"
