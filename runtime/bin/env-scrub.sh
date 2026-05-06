#!/usr/bin/env bash
# Source this from agent wrappers before launching tool processes.

agent_harness_is_sensitive_env() {
  if [[ "$1" == NODE_* && "$1" != "NODE_ENV" ]]; then
    return 0
  fi
  case "$1" in
    GITHUB_TOKEN|GH_TOKEN|HOMEBREW_GITHUB_API_TOKEN|NPM_TOKEN|BUILDKITE_TOKEN|BUILDKITE_AGENT_TOKEN|BUILDKITE_API_TOKEN|CIRCLE_TOKEN|SSH_AUTH_SOCK|GIT_ASKPASS|PGPASSWORD|DATABASE_URL|MONGODB_URI|NODE_OPTIONS|NODE_PATH|NODE_EXTRA_CA_CERTS|NODE_TLS_REJECT_UNAUTHORIZED|AGENT_HARNESS_ALLOW_MCP_WRITE|SLACK_*|AWS_*|GOOGLE_*|GCP_*|AZURE_*|NPM_CONFIG_*AUTH*|*_ACCESS_TOKEN|*_REFRESH_TOKEN|*_ID_TOKEN|*_SECRET|*_PASSWORD|*_AUTHORIZATION|*_API_KEY|*_KEY|*_TOKEN|*_PRIVATE_KEY|*_SESSION|*_COOKIE|*_CREDENTIALS|*_CREDENTIAL)
      return 0
      ;;
  esac
  return 1
}

agent_harness_is_allowed_env() {
  case "$1" in
    HOME|PATH|PWD|SHELL|TMPDIR|USER|LOGNAME|LANG|LC_ALL|LC_CTYPE|TERM|TERM_PROGRAM|XDG_CONFIG_HOME|XDG_CACHE_HOME|XDG_DATA_HOME|NODE_ENV|AGENT_HARNESS_ROOT|AGENT_HARNESS_SOURCE|AGENT_HARNESS_WORKSPACE|AGENT_HARNESS_TASK_ID|AGENT_HARNESS_MODE|NVM_*|PYENV_*|VOLTA_*|PNPM_*|COREPACK_*)
      return 0
      ;;
  esac
  return 1
}

agent_harness_scrub_env() {
  local name
  while IFS='=' read -r name _; do
    if ! agent_harness_is_allowed_env "$name" || agent_harness_is_sensitive_env "$name"; then
      unset "$name" || true
    fi
  done < <(env)

  unset AGENT_HARNESS_ALLOW_UNTASKED || true
  unset AGENT_HARNESS_ALLOW_NATIVE_WORKTREE || true
  unset AGENT_HARNESS_ALLOW_MAIN_CHECKOUT || true
  unset AGENT_HARNESS_ALLOW_MCP_WRITE || true
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "env-scrub.sh is source-only. Source it from a wrapper and call agent_harness_scrub_env." >&2
  exit 2
fi
