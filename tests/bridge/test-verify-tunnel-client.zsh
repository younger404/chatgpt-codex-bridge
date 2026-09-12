#!/bin/zsh

set -u

readonly TEST_ROOT="$(mktemp -d /tmp/chatgpt-code-tunnel-verify-test.XXXXXX)"
readonly CANONICAL_TEST_ROOT="${TEST_ROOT:A}"
readonly REPO_ROOT="${0:A:h:h:h}"
readonly VERIFIER="${REPO_ROOT}/scripts/bridge/verify-tunnel-client.zsh"
readonly RUNBOOK="${REPO_ROOT}/docs/runbooks/secure-mcp-tunnel.md"
typeset -i failures=0

cleanup() {
  local target="${TEST_ROOT}"
  local parent="${target:h:A}"
  local leaf="${target:t}"
  local prefix="chatgpt-code-tunnel-verify-test."
  local suffix="${leaf#${prefix}}"
  if [[ "${parent}" != "/private/tmp" && "${parent}" != "/tmp" ]] \
    || [[ "${leaf}" != ${prefix}* ]] \
    || [[ -z "${suffix}" || "${suffix}" == "${leaf}" ]]; then
    print -u2 -r -- "REFUSE CLEANUP: unexpected test root"
    return 1
  fi
  if [[ -d "${target}" && ! -L "${target}" ]]; then
    rm -rf -- "${target:?}"
  fi
}
trap cleanup EXIT

pass() {
  print -r -- "PASS: $1"
}

fail() {
  print -u2 -r -- "FAIL: $1"
  (( failures += 1 ))
}

assert_equal() {
  local expected="$1"
  local actual="$2"
  local label="$3"
  if [[ "${actual}" == "${expected}" ]]; then
    pass "${label}"
  else
    fail "${label} (expected=${expected:q}, actual=${actual:q})"
  fi
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if [[ "${haystack}" == *"${needle}"* ]]; then
    pass "${label}"
  else
    fail "${label} (missing=${needle:q})"
  fi
}

assert_not_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if [[ "${haystack}" == *"${needle}"* ]]; then
    fail "${label} (unexpected=${needle:q})"
  else
    pass "${label}"
  fi
}

make_fake_binary() {
  local target="$1"
  local version_output="$2"
  local exit_status="${3:-0}"
  {
    print -r -- '#!/bin/zsh'
    print -r -- '[[ "$*" == "--version" ]] || exit 64'
    print -r -- "print -r -- ${version_output:q}"
    print -r -- "exit ${exit_status}"
  } > "${target}"
  chmod 755 "${target}"
}

make_release_fixture() {
  local fixture_root="$1"
  local version="${2:-0.0.10}"
  local asset="tunnel-client-v${version}-darwin-arm64.zip"
  local payload_dir="${fixture_root}/payload"
  mkdir -p -- "${payload_dir}" "${fixture_root}/install"
  make_fake_binary "${payload_dir}/tunnel-client" "${version}+fixture"
  (
    cd "${payload_dir}" || exit 1
    /usr/bin/zip -q "${fixture_root}/${asset}" tunnel-client
  )
  cp -- "${payload_dir}/tunnel-client" "${fixture_root}/install/tunnel-client"
  local digest
  digest="$(LANG=C LC_ALL=C /usr/bin/shasum -a 256 "${fixture_root}/${asset}")"
  digest="${digest%% *}"
  print -r -- "${digest}  ${asset}" > "${fixture_root}/SHA256SUMS.txt"
}

refresh_checksum() {
  local fixture_root="$1"
  local version="$2"
  local asset="tunnel-client-v${version}-darwin-arm64.zip"
  local digest
  digest="$(LANG=C LC_ALL=C /usr/bin/shasum -a 256 "${fixture_root}/${asset}")"
  digest="${digest%% *}"
  print -r -- "${digest}  ${asset}" > "${fixture_root}/SHA256SUMS.txt"
}

make_official_bundle_fixture() {
  local fixture_root="$1"
  local version="0.0.11"
  local asset="tunnel-client-v${version}-darwin-arm64.zip"
  local payload_dir="${fixture_root}/payload"
  mkdir -p -- "${payload_dir}" "${fixture_root}/install"
  make_fake_binary "${payload_dir}/tunnel-client" "${version}+fixture"
  {
    print -r -- '#!/bin/zsh'
    print -r -- "print -r -- executed > ${fixture_root:q}/cloudflared-executed"
    print -r -- 'exit 0'
  } > "${payload_dir}/cloudflared"
  chmod 755 "${payload_dir}/cloudflared"
  print -r -- '{"version":"fixture"}' > "${payload_dir}/cloudflared-manifest.json"
  print -r -- 'fixture license' > "${payload_dir}/LICENSE"
  (
    cd "${payload_dir}" || exit 1
    /usr/bin/zip -q "${fixture_root}/${asset}" \
      tunnel-client cloudflared cloudflared-manifest.json LICENSE
  )
  cp -- "${payload_dir}/tunnel-client" "${fixture_root}/install/tunnel-client"
  refresh_checksum "${fixture_root}" "${version}"
}

run_full_verifier() {
  local fixture_root="$1"
  local output_file="$2"
  local version="${3:-0.0.10}"
  BRIDGE_TEST_SECRET="do-not-print-tunnel-key-773" \
    /bin/zsh "${VERIFIER}" \
      --binary "${fixture_root}/install/tunnel-client" \
      --archive "${fixture_root}/tunnel-client-v${version}-darwin-arm64.zip" \
      --checksums "${fixture_root}/SHA256SUMS.txt" > "${output_file}" 2>&1
}

valid_root="${CANONICAL_TEST_ROOT}/valid"
mkdir -p -- "${valid_root}"
make_release_fixture "${valid_root}"
valid_output_file="${TEST_ROOT}/valid.out"
run_full_verifier "${valid_root}" "${valid_output_file}"
valid_status=$?
valid_output="$(<"${valid_output_file}")"

assert_equal "0" "${valid_status}" "verified official release fixture exits successfully"
assert_contains "${valid_output}" "binary_path=${valid_root:A}/install/tunnel-client" "verifier reports the absolute executable path"
assert_contains "${valid_output}" "version=0.0.10" "verifier reports a normalized parseable version"
assert_contains "${valid_output}" "capability_status=PASS" "executable version capability passes"
assert_contains "${valid_output}" "checksum_status=PASS" "official checksum evidence passes"
assert_contains "${valid_output}" "archive_status=PASS" "single-file archive evidence passes"
assert_contains "${valid_output}" "payload_status=PASS" "installed binary matches the release payload"
assert_contains "${valid_output}" "provenance_status=PASS" "provenance evidence passes"
assert_contains "${valid_output}" "artifact_provenance_status=PASS" "artifact provenance has an independent PASS status"
assert_contains "${valid_output}" "runtime_capability_status=PASS" "runtime capability has an independent PASS status"
assert_contains "${valid_output}" "overall_status=PASS" "fully verified fixture reports PASS"
assert_not_contains "${valid_output}" "do-not-print-tunnel-key-773" "verifier never prints unrelated environment secrets"
assert_not_contains "${valid_output}" "SHA256SUMS.txt" "verifier does not print evidence-file paths"

capability_output_file="${TEST_ROOT}/capability-only.out"
BRIDGE_TEST_SECRET="do-not-print-tunnel-key-774" \
  /bin/zsh "${VERIFIER}" --binary "${valid_root}/install/tunnel-client" > "${capability_output_file}" 2>&1
capability_status=$?
capability_output="$(<"${capability_output_file}")"
assert_equal "2" "${capability_status}" "capability-only check exits UNVERIFIED"
assert_contains "${capability_output}" "capability_status=PASS" "capability-only check proves executable behavior"
assert_contains "${capability_output}" "provenance_status=UNVERIFIED" "capability-only check does not invent official provenance"
assert_contains "${capability_output}" "overall_status=UNVERIFIED" "capability-only result is not reported as PASS"
assert_not_contains "${capability_output}" "do-not-print-tunnel-key-774" "capability-only check does not print environment secrets"

relative_output_file="${TEST_ROOT}/relative.out"
(
  cd "${valid_root}/install" || exit 1
  /bin/zsh "${VERIFIER}" --binary ./tunnel-client
) > "${relative_output_file}" 2>&1
relative_status=$?
if (( relative_status != 0 )); then
  pass "relative binary path is rejected"
else
  fail "relative binary path is rejected"
fi
assert_contains "$(<"${relative_output_file}")" "binary_path=INVALID" "relative path is not echoed or normalized into acceptance"

nonexec_root="${CANONICAL_TEST_ROOT}/nonexec"
mkdir -p -- "${nonexec_root}"
make_fake_binary "${nonexec_root}/tunnel-client" "0.0.10"
chmod 644 "${nonexec_root}/tunnel-client"
nonexec_output_file="${TEST_ROOT}/nonexec.out"
/bin/zsh "${VERIFIER}" --binary "${nonexec_root}/tunnel-client" > "${nonexec_output_file}" 2>&1
nonexec_status=$?
if (( nonexec_status != 0 )); then
  pass "non-executable file is rejected"
else
  fail "non-executable file is rejected"
fi
assert_contains "$(<"${nonexec_output_file}")" "capability_status=FAIL" "non-executable file reports capability failure"

bad_version_root="${CANONICAL_TEST_ROOT}/bad-version"
mkdir -p -- "${bad_version_root}"
make_fake_binary "${bad_version_root}/tunnel-client" "development-build"
bad_version_output_file="${TEST_ROOT}/bad-version.out"
/bin/zsh "${VERIFIER}" --binary "${bad_version_root}/tunnel-client" > "${bad_version_output_file}" 2>&1
bad_version_status=$?
if (( bad_version_status != 0 )); then
  pass "unparseable version is rejected"
else
  fail "unparseable version is rejected"
fi
assert_contains "$(<"${bad_version_output_file}")" "version=UNPARSEABLE" "unparseable version is reported without raw output"

version_failure_root="${CANONICAL_TEST_ROOT}/version-failure"
mkdir -p -- "${version_failure_root}"
make_fake_binary "${version_failure_root}/tunnel-client" "0.0.10" 7
version_failure_output_file="${TEST_ROOT}/version-failure.out"
/bin/zsh "${VERIFIER}" --binary "${version_failure_root}/tunnel-client" > "${version_failure_output_file}" 2>&1
version_failure_status=$?
if (( version_failure_status != 0 )); then
  pass "failing --version command is rejected"
else
  fail "failing --version command is rejected"
fi
assert_contains "$(<"${version_failure_output_file}")" "capability_status=FAIL" "failed --version reports capability failure"

checksum_root="${CANONICAL_TEST_ROOT}/checksum-mismatch"
mkdir -p -- "${checksum_root}"
make_release_fixture "${checksum_root}"
execution_marker="${checksum_root}/unverified-executed"
{
  print -r -- '#!/bin/zsh'
  print -r -- "print -r -- executed > ${execution_marker:q}"
  print -r -- 'print -r -- 0.0.10'
} > "${checksum_root}/payload/tunnel-client"
chmod 755 "${checksum_root}/payload/tunnel-client"
cp -- "${checksum_root}/payload/tunnel-client" "${checksum_root}/install/tunnel-client"
(
  cd "${checksum_root}/payload" || exit 1
  /usr/bin/zip -q -FS "${checksum_root}/tunnel-client-v0.0.10-darwin-arm64.zip" tunnel-client
)
print -r -- "$(printf '0%.0s' {1..64})  tunnel-client-v0.0.10-darwin-arm64.zip" > "${checksum_root}/SHA256SUMS.txt"
checksum_output_file="${TEST_ROOT}/checksum-mismatch.out"
run_full_verifier "${checksum_root}" "${checksum_output_file}"
checksum_status=$?
if (( checksum_status != 0 )); then
  pass "checksum mismatch is rejected"
else
  fail "checksum mismatch is rejected"
fi
assert_contains "$(<"${checksum_output_file}")" "checksum_status=FAIL" "checksum mismatch reports failure"
assert_contains "$(<"${checksum_output_file}")" "overall_status=FAIL" "checksum mismatch cannot be called official"
[[ ! -e "${execution_marker}" ]] \
  && pass "checksum failure never executes the unverified candidate" \
  || fail "checksum failure never executes the unverified candidate"

bundle_root="${CANONICAL_TEST_ROOT}/official-bundle"
mkdir -p -- "${bundle_root}"
make_official_bundle_fixture "${bundle_root}"
bundle_output_file="${TEST_ROOT}/official-bundle.out"
run_full_verifier "${bundle_root}" "${bundle_output_file}" "0.0.11"
bundle_status=$?
bundle_output="$(<"${bundle_output_file}")"
assert_equal "0" "${bundle_status}" "official v0.0.11 four-file archive passes"
assert_contains "${bundle_output}" "archive_status=PASS" "official four-file archive shape passes"
assert_contains "${bundle_output}" "payload_status=PASS" "official four-file tunnel-client payload matches"
assert_contains "${bundle_output}" "artifact_provenance_status=PASS" "official four-file provenance passes"
[[ ! -e "${bundle_root}/cloudflared-executed" ]] \
  && pass "verifier never executes bundled cloudflared" \
  || fail "verifier never executes bundled cloudflared"

multi_root="${CANONICAL_TEST_ROOT}/fifth-unknown-file"
mkdir -p -- "${multi_root}"
make_official_bundle_fixture "${multi_root}"
print -r -- "unexpected" > "${multi_root}/payload/extra.txt"
(
  cd "${multi_root}/payload" || exit 1
  /usr/bin/zip -q -u "${multi_root}/tunnel-client-v0.0.11-darwin-arm64.zip" extra.txt
)
refresh_checksum "${multi_root}" "0.0.11"
multi_output_file="${TEST_ROOT}/multi-file.out"
run_full_verifier "${multi_root}" "${multi_output_file}" "0.0.11"
multi_status=$?
if (( multi_status != 0 )); then
  pass "fifth unknown archive entry is rejected"
else
  fail "fifth unknown archive entry is rejected"
fi
assert_contains "$(<"${multi_output_file}")" "archive_status=FAIL" "fifth unknown archive entry reports failure"

for unsafe_case in traversal absolute duplicate; do
  unsafe_root="${CANONICAL_TEST_ROOT}/${unsafe_case}"
  mkdir -p -- "${unsafe_root}/install"
  make_fake_binary "${unsafe_root}/install/tunnel-client" "0.0.11+fixture"
  /usr/bin/python3 - "${unsafe_root}" "${unsafe_case}" <<'PY'
import pathlib
import sys
import zipfile

root = pathlib.Path(sys.argv[1])
case = sys.argv[2]
archive = root / "tunnel-client-v0.0.11-darwin-arm64.zip"
payload = (root / "install/tunnel-client").read_bytes()
entries = [
    ("tunnel-client", payload),
    ("cloudflared", b"not executed"),
    ("cloudflared-manifest.json", b"{}"),
    ("LICENSE", b"fixture"),
]
if case == "traversal":
    entries[-1] = ("../LICENSE", b"fixture")
elif case == "absolute":
    entries[-1] = ("/LICENSE", b"fixture")
elif case == "duplicate":
    entries.append(("LICENSE", b"duplicate"))
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
    for name, data in entries:
        output.writestr(name, data)
PY
  refresh_checksum "${unsafe_root}" "0.0.11"
  unsafe_output_file="${TEST_ROOT}/${unsafe_case}.out"
  run_full_verifier "${unsafe_root}" "${unsafe_output_file}" "0.0.11"
  unsafe_status=$?
  (( unsafe_status != 0 )) \
    && pass "${unsafe_case} archive entry is rejected" \
    || fail "${unsafe_case} archive entry is rejected"
  assert_contains "$(<"${unsafe_output_file}")" "archive_status=FAIL" "${unsafe_case} reports archive failure"
done

symlink_root="${CANONICAL_TEST_ROOT}/symlink-entry"
mkdir -p -- "${symlink_root}/payload" "${symlink_root}/install"
make_fake_binary "${symlink_root}/payload/tunnel-client" "0.0.11+fixture"
cp -- "${symlink_root}/payload/tunnel-client" "${symlink_root}/install/tunnel-client"
print -r -- 'not executed' > "${symlink_root}/payload/cloudflared-target"
/bin/ln -s cloudflared-target "${symlink_root}/payload/cloudflared"
print -r -- '{}' > "${symlink_root}/payload/cloudflared-manifest.json"
print -r -- 'fixture' > "${symlink_root}/payload/LICENSE"
(
  cd "${symlink_root}/payload" || exit 1
  /usr/bin/zip -q -y "${symlink_root}/tunnel-client-v0.0.11-darwin-arm64.zip" \
    tunnel-client cloudflared cloudflared-manifest.json LICENSE
)
refresh_checksum "${symlink_root}" "0.0.11"
symlink_output_file="${TEST_ROOT}/symlink-entry.out"
run_full_verifier "${symlink_root}" "${symlink_output_file}" "0.0.11"
symlink_status=$?
(( symlink_status != 0 )) \
  && pass "symlink archive entry is rejected" \
  || fail "symlink archive entry is rejected"
assert_contains "$(<"${symlink_output_file}")" "archive_status=FAIL" "symlink reports archive failure"

blocked_root="${CANONICAL_TEST_ROOT}/gatekeeper-blocked"
mkdir -p -- "${blocked_root}/payload" "${blocked_root}/install"
{
  print -r -- '#!/bin/zsh'
  print -r -- '[[ "$*" == "--version" ]] || exit 64'
  print -r -- 'kill -9 $$'
} > "${blocked_root}/payload/tunnel-client"
chmod 755 "${blocked_root}/payload/tunnel-client"
cp -- "${blocked_root}/payload/tunnel-client" "${blocked_root}/install/tunnel-client"
print -r -- 'not executed' > "${blocked_root}/payload/cloudflared"
print -r -- '{}' > "${blocked_root}/payload/cloudflared-manifest.json"
print -r -- 'fixture' > "${blocked_root}/payload/LICENSE"
(
  cd "${blocked_root}/payload" || exit 1
  /usr/bin/zip -q "${blocked_root}/tunnel-client-v0.0.11-darwin-arm64.zip" \
    tunnel-client cloudflared cloudflared-manifest.json LICENSE
)
refresh_checksum "${blocked_root}" "0.0.11"
blocked_output_file="${TEST_ROOT}/gatekeeper-blocked.out"
run_full_verifier "${blocked_root}" "${blocked_output_file}" "0.0.11"
blocked_status=$?
assert_equal "3" "${blocked_status}" "OS-policy-blocked verified artifact has a distinct exit"
blocked_output="$(<"${blocked_output_file}")"
assert_contains "${blocked_output}" "artifact_provenance_status=PASS" "blocked runtime preserves artifact provenance PASS"
assert_contains "${blocked_output}" "runtime_capability_status=BLOCKED_BY_OS_POLICY" "blocked runtime is classified separately"
assert_contains "${blocked_output}" "gatekeeper_status=BLOCKED" "blocked runtime reports Gatekeeper status"
assert_contains "${blocked_output}" "overall_status=RUNTIME_BLOCKED" "blocked runtime is not mislabeled provenance failure"

payload_root="${CANONICAL_TEST_ROOT}/payload-mismatch"
mkdir -p -- "${payload_root}"
make_release_fixture "${payload_root}"
make_fake_binary "${payload_root}/install/tunnel-client" "0.0.10+different-payload"
payload_output_file="${TEST_ROOT}/payload-mismatch.out"
run_full_verifier "${payload_root}" "${payload_output_file}"
payload_status=$?
if (( payload_status != 0 )); then
  pass "installed binary mismatch is rejected"
else
  fail "installed binary mismatch is rejected"
fi
assert_contains "$(<"${payload_output_file}")" "payload_status=FAIL" "installed binary mismatch reports failure"
assert_contains "$(<"${payload_output_file}")" "provenance_status=FAIL" "binary mismatch fails provenance"

for forbidden in \
  'xattr -d com.apple.quarantine' \
  'spctl --add' \
  'spctl --enable' \
  'codesign --force' \
  'Open Anyway'; do
  if /usr/bin/grep -R -F -q -- "${forbidden}" \
    "${REPO_ROOT}/scripts/bridge" \
    "${REPO_ROOT}/plugins/chatgpt-codex-bridge/scripts" \
    "${RUNBOOK}"; then
    fail "runtime scripts and runbook do not provide prohibited Gatekeeper bypass: ${forbidden}"
  else
    pass "runtime scripts and runbook do not provide prohibited Gatekeeper bypass: ${forbidden}"
  fi
done

if (( failures > 0 )); then
  print -u2 -r -- "RESULT: FAIL (${failures} assertions)"
  exit 1
fi

print -r -- "RESULT: PASS"
