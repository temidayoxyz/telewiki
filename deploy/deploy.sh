#!/usr/bin/env bash
#
# TeleWiki deploy — runs on the VM after a push to main.
#
# Pulls the latest commit, installs pinned dependencies, restarts the systemd
# service, and rolls back to the previous commit if the bot fails to come back
# up. Safe to run repeatedly: a no-op push just restarts the service.
#
# Status queries (systemctl is-active / show) work unprivileged, so only
# `restart` needs sudo — keep the sudoers rule that narrow.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/telewiki}"
VENV="${VENV:-$APP_DIR/.venv}"
SERVICE="${SERVICE:-telewiki}"
BRANCH="${BRANCH:-main}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-30}"

PIP="$VENV/bin/pip"
HEALTH_GRACE=3

log() { printf '%s [deploy] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*"; exit 1; }

# One deploy at a time. A second push arriving mid-deploy should queue behind
# the first rather than fight it over the git working tree and systemd.
lockfile="$(mktemp -t telewiki-deploy.XXXXXX)"
trap 'rm -f "$lockfile"' EXIT
if ! flock -n "$lockfile"; then
    log "another deploy is already running — skipping this push"
    exit 0
fi

cd "$APP_DIR"
command -v git >/dev/null || die "git not found"
[ -x "$PIP" ] || die "virtualenv not found at $VENV (expected $PIP)"

# A mistyped APP_DIR would otherwise run `git reset --hard` against whatever
# happens to live there. Refuse unless this really is the TeleWiki checkout.
if [ ! -f "$APP_DIR/main.py" ] || [ ! -d "$APP_DIR/telewiki" ]; then
    die "$APP_DIR does not look like the TeleWiki repo (main.py and telewiki/ missing) — refusing to run git reset here"
fi

# Remember where we are, so we can put it back if the new version is unhealthy.
previous="$(git rev-parse HEAD)"
restarts_before="$(systemctl show -p NRestarts --value "$SERVICE" 2>/dev/null || echo 0)"
log "current commit ${previous:0:7}, $restarts_before restart(s) so far"

restore() {
    log "rolling back to ${previous:0:7}"
    git reset --quiet --hard "$previous" || log "WARNING: could not check out $previous"
    "$PIP" install --quiet --requirement requirements.txt || log "WARNING: dependency restore failed"
    sudo systemctl restart "$SERVICE" || log "WARNING: restart failed"
    sleep 3
    if systemctl is-active --quiet "$SERVICE"; then
        log "rollback OK — the previous version is running again"
    else
        log "ROLLBACK FAILED — inspect: journalctl -u $SERVICE -n 50 --no-pager"
    fi
}

log "fetching origin/$BRANCH"
git fetch --quiet origin "$BRANCH"
target="$(git rev-parse "origin/$BRANCH")"

if [ "$target" = "$previous" ]; then
    # Still restart: a push that only touches docs can follow a manual
    # config change, and a restart is cheap.
    log "already at ${target:0:7} — restarting to pick up config changes"
else
    log "deploying ${previous:0:7} -> ${target:0:7}"
fi

if ! git reset --quiet --hard "$target" \
    || ! "$PIP" install --quiet --requirement requirements.txt; then
    log "failed to prepare ${target:0:7}"
    restore
    exit 1
fi

log "restarting $SERVICE"
sudo systemctl restart "$SERVICE"

# "active" alone is not enough: a bot that starts and immediately crashes looks
# active during the systemd restart window. Require that no new restart has
# been counted, which catches that class of failure.
sleep "$HEALTH_GRACE"
deadline=$((SECONDS + HEALTH_TIMEOUT))
while [ "$SECONDS" -lt "$deadline" ]; do
    if ! systemctl is-active --quiet "$SERVICE"; then
        log "service is not active — failing"
        restore
        exit 1
    fi
    restarts_now="$(systemctl show -p NRestarts --value "$SERVICE")"
    if [ "$restarts_now" -ne "$restarts_before" ]; then
        log "service crashed and restarted ($restarts_before -> $restarts_now) — failing"
        restore
        exit 1
    fi
    sleep 2
done

log "healthy at ${target:0:7}"
