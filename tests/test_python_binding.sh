#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
REQUIRED_PYTHON="${AGENT_HARNESS_PYTHON:?test requires the canonical Python binding}"
TMP_BASE="${TMPDIR:-/tmp}"
TMP_DIR="${TMP_BASE%/}/agent-harness-python-binding-$$"
mkdir -p "$TMP_DIR"
TMP_DIR="$(cd "$TMP_DIR" && pwd -P)"
FAKE_BIN="$TMP_DIR/fake-bin"
OUT="$TMP_DIR/output"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$FAKE_BIN"
cat >"$FAKE_BIN/python3" <<'SH'
#!/usr/bin/env bash
echo "AMBIENT_PYTHON_USED" >&2
exit 91
SH
chmod +x "$FAKE_BIN/python3"

make_root() {
  local case_root="$1"
  mkdir -p "$case_root/tests/unit" "$case_root/src"
  cp "$ROOT/tests/run.sh" "$case_root/tests/run.sh"
  cat >"$case_root/tests/unit/test_binding_probe.py" <<'PY'
import unittest


class BindingProbeTests(unittest.TestCase):
    def test_unit_subprocess_uses_bound_interpreter(self):
        print("BOUND_UNIT_SUBPROCESS_RAN")
PY
}

run_case() {
  local case_root="$1"
  shift
  set +e
  env "$@" PATH="$FAKE_BIN:/usr/bin:/bin" bash "$case_root/tests/run.sh" >"$OUT" 2>&1
  CASE_STATUS=$?
  set -e
}

expect_rejected() {
  local label="$1"
  local expected="$2"
  shift 2
  local case_root="$TMP_DIR/$label"
  make_root "$case_root"
  run_case "$case_root" "$@"
  if [ "$CASE_STATUS" -eq 0 ] || ! grep -Fq "$expected" "$OUT"; then
    echo "$label: expected runner rejection containing: $expected" >&2
    cat "$OUT" >&2
    exit 1
  fi
}

PRE_FIRST_EXEC="$TMP_DIR/pre-first-exec-python"
cp "$REQUIRED_PYTHON" "$PRE_FIRST_EXEC"
cat >"$PRE_FIRST_EXEC.replacement" <<'SH'
#!/usr/bin/env bash
echo "PRE_FIRST_EXEC_REPLACEMENT_RAN" >&2
exit 94
SH
chmod +x "$PRE_FIRST_EXEC" "$PRE_FIRST_EXEC.replacement"
PRE_FIRST_EXEC_ROOT="$TMP_DIR/pre-first-exec"
make_root "$PRE_FIRST_EXEC_ROOT"
"$REQUIRED_PYTHON" - "$PRE_FIRST_EXEC_ROOT/tests/run.sh" \
  "$PRE_FIRST_EXEC" <<'PY'
from pathlib import Path
import sys

runner = Path(sys.argv[1])
interpreter = sys.argv[2]
source = runner.read_text()
marker = (
    'PYTHON_IDENTITY="$(python_identity)" ||\n'
    '  python_binding_error "AGENT_HARNESS_PYTHON identity unavailable"\n'
)
replacement = (
    marker
    + f'/bin/mv "{interpreter}.replacement" "{interpreter}"\n'
    + f'/bin/chmod +x "{interpreter}"\n'
)
if source.count(marker) != 1:
    raise SystemExit("runner identity marker is missing or ambiguous")
runner.write_text(source.replace(marker, replacement))
PY
run_case "$PRE_FIRST_EXEC_ROOT" AGENT_HARNESS_PYTHON="$PRE_FIRST_EXEC"
PRE_FIRST_EXEC_FAILED=0
if [ "$CASE_STATUS" -eq 0 ] ||
   ! grep -Fq "AGENT_HARNESS_PYTHON changed after validation" "$OUT"; then
  echo "pre-first-exec: expected rejection before interpreter execution" >&2
  cat "$OUT" >&2
  PRE_FIRST_EXEC_FAILED=1
fi
if grep -Fq "PRE_FIRST_EXEC_REPLACEMENT_RAN" "$OUT"; then
  echo "pre-first-exec: replacement interpreter must not run" >&2
  cat "$OUT" >&2
  PRE_FIRST_EXEC_FAILED=1
fi
[ "$PRE_FIRST_EXEC_FAILED" -eq 0 ] || exit 1

expect_rejected missing "AGENT_HARNESS_PYTHON must be set" -u AGENT_HARNESS_PYTHON

RELATIVE_PYTHON="$TMP_DIR/relative-python"
cp "$REQUIRED_PYTHON" "$RELATIVE_PYTHON"
chmod +x "$RELATIVE_PYTHON"
expect_rejected relative "AGENT_HARNESS_PYTHON must be an absolute path" \
  AGENT_HARNESS_PYTHON="relative-python"

ALIASED_PYTHON="$TMP_DIR/aliased-python"
ln -s "$REQUIRED_PYTHON" "$ALIASED_PYTHON"
expect_rejected symlink "AGENT_HARNESS_PYTHON must be its canonical real path" \
  AGENT_HARNESS_PYTHON="$ALIASED_PYTHON"

NONEXECUTABLE="$TMP_DIR/nonexecutable-python"
printf '#!/usr/bin/env bash\nexit 0\n' >"$NONEXECUTABLE"
chmod 600 "$NONEXECUTABLE"
expect_rejected nonexecutable "AGENT_HARNESS_PYTHON must be executable" \
  AGENT_HARNESS_PYTHON="$NONEXECUTABLE"

TOO_OLD="$TMP_DIR/python-3.9"
cat >"$TOO_OLD" <<'SH'
#!/usr/bin/env bash
identity="$(/usr/bin/stat -f '%d:%i' "$0")"
printf '%s\t3\t9\t%s\n' "$0" "$identity"
SH
chmod +x "$TOO_OLD"
expect_rejected too-old "AGENT_HARNESS_PYTHON requires Python 3.10 or newer" \
  AGENT_HARNESS_PYTHON="$TOO_OLD"

CHANGING="$TMP_DIR/changing-python"
cat >"$CHANGING" <<SH
#!/usr/bin/env bash
"$REQUIRED_PYTHON" "\$@"
status=\$?
/bin/mv "\$0.replacement" "\$0"
/bin/chmod +x "\$0"
exit "\$status"
SH
cat >"$CHANGING.replacement" <<'SH'
#!/usr/bin/env bash
exit 92
SH
chmod +x "$CHANGING" "$CHANGING.replacement"
expect_rejected changed "AGENT_HARNESS_PYTHON changed after validation" \
  AGENT_HARNESS_PYTHON="$CHANGING"

LATE_CHANGING="$TMP_DIR/late-changing-python"
cp "$REQUIRED_PYTHON" "$LATE_CHANGING"
printf '#!/usr/bin/env bash\nexit 93\n' >"$LATE_CHANGING.replacement"
chmod +x "$LATE_CHANGING" "$LATE_CHANGING.replacement"
LATE_ROOT="$TMP_DIR/late-changing"
make_root "$LATE_ROOT"
"$REQUIRED_PYTHON" - "$LATE_ROOT/tests/run.sh" \
  "$LATE_CHANGING" <<'PY'
from pathlib import Path
import sys

runner = Path(sys.argv[1])
interpreter = sys.argv[2]
source = runner.read_text()
marker = "readonly AGENT_HARNESS_PYTHON\n"
replacement = (
    marker
    + f'/bin/mv "{interpreter}.replacement" "{interpreter}"\n'
    + f'/bin/chmod +x "{interpreter}"\n'
)
if source.count(marker) != 1:
    raise SystemExit("runner validation marker is missing or ambiguous")
runner.write_text(source.replace(marker, replacement))
PY
run_case "$LATE_ROOT" AGENT_HARNESS_PYTHON="$LATE_CHANGING"
if [ "$CASE_STATUS" -eq 0 ] ||
   ! grep -Fq "AGENT_HARNESS_PYTHON changed after validation" "$OUT"; then
  echo "late-changing: expected rejection before unit subprocess" >&2
  cat "$OUT" >&2
  exit 1
fi

CANONICAL_ROOT="$TMP_DIR/canonical"
make_root "$CANONICAL_ROOT"
run_case "$CANONICAL_ROOT" AGENT_HARNESS_PYTHON="$REQUIRED_PYTHON"
if ! grep -Fq "BOUND_UNIT_SUBPROCESS_RAN" "$OUT"; then
  echo "canonical: bound interpreter did not run the unit-test subprocess" >&2
  cat "$OUT" >&2
  exit 1
fi

echo "python binding tests passed"
