#!/bin/bash
# ============================================================
# FaultRay Test Proof Generator
# ② SHA-256 hash proof of test results
# ④ Test count regression guard
#
# Produces a tamper-evident test report:
#   - SHA-256 hash of results
#   - Timestamp
#   - Commit hash
#   - Test count must be >= MIN_TESTS (blocks if not)
#
# Usage:
#   ./scripts/test-proof.sh          # Run tests + generate proof
#   ./scripts/test-proof.sh --check  # Check latest proof only
# ============================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

PROOF_DIR="$PROJECT_ROOT/.faultray-proof"
PROOF_FILE="$PROOF_DIR/latest-proof.json"
PROOF_LOG="$PROOF_DIR/proof-history.jsonl"
MIN_TESTS=31000

mkdir -p "$PROOF_DIR"

# ── Check mode ──
if [ "${1:-}" = "--check" ]; then
  if [ -f "$PROOF_FILE" ]; then
    echo "Latest test proof:"
    python3 -m json.tool "$PROOF_FILE"

    # Verify hash
    STORED_HASH=$(python3 -c "import json; print(json.load(open('$PROOF_FILE'))['proof_hash'])")
    PAYLOAD=$(python3 -c "
import json
d = json.load(open('$PROOF_FILE'))
del d['proof_hash']
print(json.dumps(d, sort_keys=True))
")
    COMPUTED_HASH=$(echo -n "$PAYLOAD" | sha256sum | cut -d' ' -f1)

    if [ "$STORED_HASH" = "$COMPUTED_HASH" ]; then
      echo ""
      echo "✅ Hash verification PASSED"
    else
      echo ""
      echo "❌ Hash verification FAILED — proof may be tampered"
      exit 1
    fi
  else
    echo "No proof file found. Run: ./scripts/test-proof.sh"
    exit 1
  fi
  exit 0
fi

# ── Run tests ──
echo "╔══════════════════════════════════════════════╗"
echo "║  FaultRay Test Proof Generator               ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")

echo "[1/4] Running full test suite..."
TEST_OUTPUT=$(python3 -m pytest tests/ -q --tb=line 2>&1)
TEST_EXIT=$?

# Extract counts
PASSED=$(echo "$TEST_OUTPUT" | grep -oP '\d+ passed' | grep -oP '\d+' || echo "0")
FAILED=$(echo "$TEST_OUTPUT" | grep -oP '\d+ failed' | grep -oP '\d+' || echo "0")
SKIPPED=$(echo "$TEST_OUTPUT" | grep -oP '\d+ skipped' | grep -oP '\d+' || echo "0")
ERRORS=$(echo "$TEST_OUTPUT" | grep -oP '\d+ error' | grep -oP '\d+' || echo "0")
DURATION=$(echo "$TEST_OUTPUT" | grep -oP '\d+\.\d+s' | tail -1 || echo "0s")
TOTAL=$((PASSED + FAILED))

echo "[2/4] Test results: $PASSED passed, $FAILED failed, $SKIPPED skipped"

# ── ④ Test count regression guard ──
echo "[3/4] Test count regression check..."
if [ "$PASSED" -lt "$MIN_TESTS" ]; then
  echo ""
  echo "╔══════════════════════════════════════════════╗"
  echo "║  ❌ TEST COUNT REGRESSION DETECTED            ║"
  echo "║  Current: $PASSED < Minimum: $MIN_TESTS"
  echo "║  Tests may have been deleted or broken.       ║"
  echo "║  This is BLOCKED.                             ║"
  echo "╚══════════════════════════════════════════════╝"
  exit 1
fi
echo "  ✅ Test count OK ($PASSED >= $MIN_TESTS)"

# ── ② Generate SHA-256 proof ──
echo "[4/4] Generating SHA-256 proof..."

# Build the payload (without hash)
PAYLOAD=$(python3 -c "
import json
proof = {
    'timestamp': '$TIMESTAMP',
    'commit': '$COMMIT',
    'branch': '$BRANCH',
    'python_version': '$(python3 --version 2>&1)',
    'tests_passed': $PASSED,
    'tests_failed': $FAILED,
    'tests_skipped': $SKIPPED,
    'tests_errors': ${ERRORS:-0},
    'tests_total': $TOTAL,
    'duration': '$DURATION',
    'min_tests_required': $MIN_TESTS,
    'test_exit_code': $TEST_EXIT,
    'ruff_clean': $(ruff check src/ tests/ --quiet 2>/dev/null && echo 'true' || echo 'false'),
}
print(json.dumps(proof, sort_keys=True))
")

# Compute hash
PROOF_HASH=$(echo -n "$PAYLOAD" | sha256sum | cut -d' ' -f1)

# Write proof file with hash
python3 -c "
import json
proof = json.loads('$PAYLOAD')
proof['proof_hash'] = '$PROOF_HASH'
with open('$PROOF_FILE', 'w') as f:
    json.dump(proof, f, indent=2)
# Append to history log
with open('$PROOF_LOG', 'a') as f:
    f.write(json.dumps(proof) + '\n')
"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  TEST PROOF GENERATED                        ║"
echo "╠══════════════════════════════════════════════╣"
printf "║  Tests:    %-6d passed / %-4d failed       ║\n" "$PASSED" "$FAILED"
printf "║  Duration: %-37s║\n" "$DURATION"
printf "║  Commit:   %-37s║\n" "${COMMIT:0:12}"
echo "║  SHA-256:  ${PROOF_HASH:0:40}...║"
echo "║  Stored:   .faultray-proof/latest-proof.json ║"
echo "╚══════════════════════════════════════════════╝"

# ── Verify own proof ──
echo ""
echo "Self-verification..."
RECOMPUTED=$(python3 -c "
import json
d = json.load(open('$PROOF_FILE'))
h = d.pop('proof_hash')
import hashlib
computed = hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()
print('PASS' if h == computed else 'FAIL')
")

if [ "$RECOMPUTED" = "PASS" ]; then
  echo "✅ Self-verification PASSED"
else
  echo "❌ Self-verification FAILED"
  exit 1
fi

exit $TEST_EXIT
