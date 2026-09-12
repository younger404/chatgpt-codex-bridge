#!/bin/zsh

set -u

readonly TEST_ROOT="$(mktemp -d /tmp/chatgpt-tunnel-source-build-test.XXXXXX)"
readonly CANONICAL_TEST_ROOT="${TEST_ROOT:A}"
readonly REPO_ROOT="${0:A:h:h:h}"
readonly BUILDER="${REPO_ROOT}/scripts/bridge/build-verified-tunnel-client.zsh"
typeset -i failures=0

cleanup() {
  local target="${TEST_ROOT}"
  local parent="${target:h:A}"
  local leaf="${target:t}"
  [[ "${parent}" == "/private/tmp" || "${parent}" == "/tmp" ]] || return 1
  [[ "${leaf}" == chatgpt-tunnel-source-build-test.* ]] || return 1
  [[ -d "${target}" && ! -L "${target}" ]] && /bin/rm -rf -- "${target:?}"
}
trap cleanup EXIT

pass() { print -r -- "PASS: $1"; }
fail() { print -u2 -r -- "FAIL: $1"; (( failures += 1 )); }
assert_equal() {
  [[ "$1" == "$2" ]] && pass "$3" || fail "$3 (expected=${1:q}, actual=${2:q})"
}
assert_contains() {
  [[ "$1" == *"$2"* ]] && pass "$3" || fail "$3 (missing=${2:q})"
}

make_source_fixture() {
  local root="$1"
  local runtime_version="${2:-0.0.11}"
  local origin="${3:-https://github.com/openai/tunnel-client.git}"
  local module_mode="${4:-valid}"
  /bin/mkdir -p -- "${root}/cmd/client" "${root}/pkg/version"
  if [[ "${module_mode}" == "valid" ]]; then
    print -r -- 'module github.com/openai/tunnel-client' > "${root}/go.mod"
    print -r -- '' >> "${root}/go.mod"
    print -r -- 'go 1.22' >> "${root}/go.mod"
  else
    print -r -- 'module' > "${root}/go.mod"
  fi
  print -r -- '0.0.11' > "${root}/pkg/version/VERSION"
  {
    print -r -- 'package main'
    print -r -- ''
    print -r -- 'import ('
    print -r -- '  "fmt"'
    print -r -- '  "os"'
    print -r -- ')'
    print -r -- ''
    print -r -- 'func main() {'
    print -r -- '  if len(os.Args) == 2 && os.Args[1] == "--version" {'
    print -r -- "    fmt.Println(\"tunnel-client ${runtime_version}\")"
    print -r -- '    return'
    print -r -- '  }'
    print -r -- '  if len(os.Args) == 3 && os.Args[1] == "help" && os.Args[2] == "quickstart" {'
    print -r -- '    fmt.Println("quickstart help")'
    print -r -- '    return'
    print -r -- '  }'
    print -r -- '  os.Exit(64)'
    print -r -- '}'
  } > "${root}/cmd/client/main.go"
  /usr/bin/git -C "${root}" init -q
  /usr/bin/git -C "${root}" config user.name 'Bridge Fixture'
  /usr/bin/git -C "${root}" config user.email 'bridge-fixture@example.invalid'
  /usr/bin/git -C "${root}" remote add origin "${origin}"
  /usr/bin/git -C "${root}" add go.mod cmd/client/main.go pkg/version/VERSION
  /usr/bin/git -C "${root}" commit -q -m fixture
  /usr/bin/git -C "${root}" tag v0.0.11
}

run_builder() {
  local source="$1"
  local output="$2"
  local commit="$3"
  BRIDGE_TEST_SECRET='do-not-record-source-build-key-991' \
    /bin/zsh "${BUILDER}" \
      --source "${source}" \
      --output "${output}" \
      --expected-version 0.0.11 \
      --expected-commit "${commit}"
}

if [[ ! -f "${BUILDER}" ]]; then
  fail "source builder exists"
else
  pass "source builder exists"
fi

valid_source="${CANONICAL_TEST_ROOT}/valid-source"
valid_output="${CANONICAL_TEST_ROOT}/valid-output/tunnel-client"
make_source_fixture "${valid_source}"
valid_commit="$(/usr/bin/git -C "${valid_source}" rev-parse HEAD)"
/bin/mkdir -p -- "${valid_output:h}"
run_builder "${valid_source}" "${valid_output}" "${valid_commit}" >"${TEST_ROOT}/valid.out" 2>&1
valid_status=$?
assert_equal "0" "${valid_status}" "exact clean official-source fixture builds"
[[ -x "${valid_output}" && ! -L "${valid_output}" ]] \
  && pass "source build creates a regular executable" \
  || fail "source build creates a regular executable"
[[ -f "${valid_output}.provenance.json" && ! -L "${valid_output}.provenance.json" ]] \
  && pass "source build creates a provenance receipt" \
  || fail "source build creates a provenance receipt"

if [[ -f "${valid_output}.provenance.json" ]]; then
  receipt_check="$(/usr/bin/python3 - "${valid_output}.provenance.json" "${valid_commit}" <<'PY'
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assert data == {
    "binarySHA256": data["binarySHA256"],
    "binaryVersion": "0.0.11",
    "goModVerify": "PASS",
    "goVersion": data["goVersion"],
    "provenanceMode": "official_source_build_v1",
    "release": "v0.0.11",
    "repository": "openai/tunnel-client",
    "runtimeCapability": "PASS",
    "sourceCommit": sys.argv[2],
    "sourceTreeClean": True,
    "versionFile": "0.0.11",
}
assert len(data["binarySHA256"]) == 64
assert data["goVersion"].startswith("go version go")
print("ok")
PY
)"
  assert_equal "ok" "${receipt_check}" "receipt uses the exact closed non-secret schema"
  receipt_text="$(<"${valid_output}.provenance.json")"
  [[ "${receipt_text}" != *'do-not-record-source-build-key-991'* \
     && "${receipt_text}" != *'HOME'* \
     && "${receipt_text}" != *'Tunnel ID'* ]] \
    && pass "receipt excludes environment secrets and private paths" \
    || fail "receipt excludes environment secrets and private paths"
fi

wrong_origin_source="${CANONICAL_TEST_ROOT}/wrong-origin-source"
make_source_fixture "${wrong_origin_source}" "0.0.11" "https://example.invalid/openai/tunnel-client.git"
wrong_origin_commit="$(/usr/bin/git -C "${wrong_origin_source}" rev-parse HEAD)"
run_builder "${wrong_origin_source}" "${CANONICAL_TEST_ROOT}/wrong-origin-output" "${wrong_origin_commit}" >"${TEST_ROOT}/wrong-origin.out" 2>&1
wrong_origin_status=$?
(( wrong_origin_status != 0 )) \
  && pass "wrong source origin is rejected" \
  || fail "wrong source origin is rejected"

run_builder "${valid_source}" "${CANONICAL_TEST_ROOT}/wrong-commit-output" "0000000000000000000000000000000000000000" >"${TEST_ROOT}/wrong-commit.out" 2>&1
wrong_commit_status=$?
(( wrong_commit_status != 0 )) \
  && pass "wrong expected source commit is rejected" \
  || fail "wrong expected source commit is rejected"

dirty_source="${CANONICAL_TEST_ROOT}/dirty-source"
/bin/cp -R "${valid_source}" "${dirty_source}"
print -r -- 'dirty' >> "${dirty_source}/pkg/version/VERSION"
run_builder "${dirty_source}" "${CANONICAL_TEST_ROOT}/dirty-output" "${valid_commit}" >"${TEST_ROOT}/dirty.out" 2>&1
dirty_status=$?
(( dirty_status != 0 )) \
  && pass "dirty source tree is rejected" \
  || fail "dirty source tree is rejected"

wrong_version_file_source="${CANONICAL_TEST_ROOT}/wrong-version-file-source"
make_source_fixture "${wrong_version_file_source}"
print -r -- '0.0.10' > "${wrong_version_file_source}/pkg/version/VERSION"
/usr/bin/git -C "${wrong_version_file_source}" add pkg/version/VERSION
/usr/bin/git -C "${wrong_version_file_source}" commit -q -m wrong-version-file
/usr/bin/git -C "${wrong_version_file_source}" tag -f v0.0.11 >/dev/null
wrong_version_file_commit="$(/usr/bin/git -C "${wrong_version_file_source}" rev-parse HEAD)"
run_builder "${wrong_version_file_source}" "${CANONICAL_TEST_ROOT}/wrong-version-file-output" "${wrong_version_file_commit}" >"${TEST_ROOT}/wrong-version-file.out" 2>&1
wrong_version_file_status=$?
(( wrong_version_file_status != 0 )) \
  && pass "wrong VERSION file is rejected" \
  || fail "wrong VERSION file is rejected"

bad_module_source="${CANONICAL_TEST_ROOT}/bad-module-source"
make_source_fixture "${bad_module_source}" "0.0.11" "https://github.com/openai/tunnel-client.git" invalid
bad_module_commit="$(/usr/bin/git -C "${bad_module_source}" rev-parse HEAD)"
run_builder "${bad_module_source}" "${CANONICAL_TEST_ROOT}/bad-module-output" "${bad_module_commit}" >"${TEST_ROOT}/bad-module.out" 2>&1
bad_module_status=$?
(( bad_module_status != 0 )) \
  && pass "go mod verify failure is rejected" \
  || fail "go mod verify failure is rejected"

wrong_runtime_source="${CANONICAL_TEST_ROOT}/wrong-runtime-source"
make_source_fixture "${wrong_runtime_source}" "0.0.10"
wrong_runtime_commit="$(/usr/bin/git -C "${wrong_runtime_source}" rev-parse HEAD)"
run_builder "${wrong_runtime_source}" "${CANONICAL_TEST_ROOT}/wrong-runtime-output" "${wrong_runtime_commit}" >"${TEST_ROOT}/wrong-runtime.out" 2>&1
wrong_runtime_status=$?
(( wrong_runtime_status != 0 )) \
  && pass "wrong built runtime version is rejected" \
  || fail "wrong built runtime version is rejected"

/bin/zsh "${BUILDER}" \
  --source "${valid_source}" \
  --output "${CANONICAL_TEST_ROOT}/arbitrary-package-output" \
  --expected-version 0.0.11 \
  --expected-commit "${valid_commit}" \
  --package ./cmd/other >"${TEST_ROOT}/arbitrary-package.out" 2>&1
arbitrary_package_status=$?
assert_equal "64" "${arbitrary_package_status}" "arbitrary build package input is rejected"

/bin/zsh "${BUILDER}" \
  --source "${valid_source}" \
  --output "${CANONICAL_TEST_ROOT}/arbitrary-flags-output" \
  --expected-version 0.0.11 \
  --expected-commit "${valid_commit}" \
  --ldflags=-s >"${TEST_ROOT}/arbitrary-flags.out" 2>&1
arbitrary_flags_status=$?
assert_equal "64" "${arbitrary_flags_status}" "arbitrary linker flags are rejected"

if (( failures > 0 )); then
  print -u2 -r -- "RESULT: FAIL (${failures} assertions)"
  exit 1
fi

print -r -- "RESULT: PASS"
