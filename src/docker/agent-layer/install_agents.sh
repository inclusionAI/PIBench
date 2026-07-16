#!/usr/bin/env sh
set -eu

log() {
    printf '[payskills-agent-layer] %s\n' "$*" >&2
}

AGENT_TYPE="${PAYSKILLS_AGENT_TYPE:-all}"

case "$AGENT_TYPE" in
    claude-code|openclaw|hermes|all)
        ;;
    *)
        log "unsupported PAYSKILLS_AGENT_TYPE: $AGENT_TYPE"
        exit 22
        ;;
esac

install_debian_packages() {
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends \
        bash ca-certificates curl git gnupg build-essential \
        python3 python3-pip python3-venv python3-dev
    if ! command -v node >/dev/null 2>&1 || ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 18 ? 0 : 1)' >/dev/null 2>&1; then
        curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
        apt-get install -y --no-install-recommends nodejs
    elif ! command -v npm >/dev/null 2>&1; then
        apt-get install -y --no-install-recommends npm
    fi
    rm -rf /var/lib/apt/lists/*
}

install_alpine_packages() {
    apk add --no-cache \
        bash ca-certificates curl git build-base \
        python3 py3-pip py3-virtualenv nodejs npm
}

install_claude_code() {
    log "installing Claude Code"
    npm install -g @anthropic-ai/claude-code@2.1.200
}

install_openclaw() {
    log "installing OpenClaw"
    npm install -g openclaw
}

install_hermes() {
    log "installing Hermes"
    python3 -m venv /opt/payskills-agent-venv
    PIP=/opt/payskills-agent-venv/bin/pip
    "$PIP" install --no-cache-dir --upgrade pip setuptools wheel
    if [ ! -d /opt/hermes-agent ]; then
        git clone --depth 1 https://github.com/NousResearch/hermes-agent.git /opt/hermes-agent
    fi
    "$PIP" install --no-cache-dir -e /opt/hermes-agent
    ln -sf /opt/payskills-agent-venv/bin/hermes /usr/local/bin/hermes
}

if command -v apt-get >/dev/null 2>&1; then
    log "installing Debian/Ubuntu runtime prerequisites"
    install_debian_packages
elif command -v apk >/dev/null 2>&1; then
    log "installing Alpine runtime prerequisites"
    install_alpine_packages
else
    log "unsupported base image: expected apt-get or apk"
    exit 20
fi

if { [ "$AGENT_TYPE" = "claude-code" ] || [ "$AGENT_TYPE" = "openclaw" ] || [ "$AGENT_TYPE" = "all" ]; } \
    && ! command -v npm >/dev/null 2>&1; then
    log "npm is required but was not installed"
    exit 21
fi

if [ "$AGENT_TYPE" = "claude-code" ] || [ "$AGENT_TYPE" = "all" ]; then
    install_claude_code
fi
if [ "$AGENT_TYPE" = "openclaw" ] || [ "$AGENT_TYPE" = "all" ]; then
    install_openclaw
fi
if [ "$AGENT_TYPE" = "hermes" ] || [ "$AGENT_TYPE" = "all" ]; then
    install_hermes
fi

mkdir -p /opt/payskills-agent-layer
cat > /opt/payskills-agent-layer/VERSION <<EOF
${PAYSKILLS_V2_AGENT_RUNTIME_VERSION:-unknown}
EOF

log "agent runtime installation completed for $AGENT_TYPE"
