#!/bin/zsh

set -u

readonly TEST_ROOT="$(mktemp -d /tmp/chatgpt-code-sandbox-check.XXXXXX)"
readonly REPO_ROOT="${0:A:h:h:h}"
readonly CHECKER="${REPO_ROOT}/scripts/bridge/check-sandbox-repo.zsh"
typeset -i failures=0

cleanup() {
  local target="${TEST_ROOT}"
  local parent="${target:h:A}"
  local leaf="${target:t}"
  local prefix="chatgpt-code-sandbox-check."
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

assert_status() {
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

make_clean_repo() {
  local repo="$1"
  local branch="${2:-codex/proof}"
  mkdir -p -- "${repo}"
  command git -C "${repo}" init -q -b "${branch}"
  command git -C "${repo}" config user.name "Boundary Test"
  command git -C "${repo}" config user.email "boundary-test@example.invalid"
  print -r -- "sandbox proof" > "${repo}/README.md"
  command git -C "${repo}" add README.md
  command git -C "${repo}" commit -q -m "test baseline"
}

run_checker() {
  local approved_root="$1"
  local repo="$2"
  local output_file="$3"
  /bin/zsh "${CHECKER}" --approved-root "${approved_root}" --repo "${repo}" > "${output_file}" 2>&1
}

approved_root="${TEST_ROOT}/approved"
mkdir -p -- "${approved_root}"

clean_repo="${approved_root}/clean-repo"
make_clean_repo "${clean_repo}"
output_file="${TEST_ROOT}/clean.out"
run_checker "${approved_root}" "${clean_repo}" "${output_file}"
clean_status=$?
clean_output="$(<"${output_file}")"
assert_status "0" "${clean_status}" "clean task-branch repository passes"
assert_contains "${clean_output}" "overall_status=PASS" "clean repository reports PASS"
assert_contains "${clean_output}" "symlink_entries=PASS" "clean repository reports no symlink entries"
assert_not_contains "${clean_output}" "${clean_repo}" "checker does not print repository path"

outside_repo="${TEST_ROOT}/outside-repo"
make_clean_repo "${outside_repo}"
output_file="${TEST_ROOT}/outside.out"
run_checker "${approved_root}" "${outside_repo}" "${output_file}"
outside_status=$?
if (( outside_status != 0 )); then
  pass "repository outside approved root is rejected"
else
  fail "repository outside approved root is rejected"
fi
assert_contains "$(<"${output_file}")" "boundary=FAIL" "outside repository reports boundary failure"

linked_target="${approved_root}/linked-target"
make_clean_repo "${linked_target}"
linked_repo="${approved_root}/linked-repo"
ln -s -- "${linked_target}" "${linked_repo}"
output_file="${TEST_ROOT}/symlink.out"
run_checker "${approved_root}" "${linked_repo}" "${output_file}"
symlink_status=$?
if (( symlink_status != 0 )); then
  pass "symlinked repository root is rejected"
else
  fail "symlinked repository root is rejected"
fi
assert_contains "$(<"${output_file}")" "symlink=FAIL" "symlinked repository reports symlink failure"

not_repo="${approved_root}/not-a-repo"
mkdir -p -- "${not_repo}"
output_file="${TEST_ROOT}/not-repo.out"
run_checker "${approved_root}" "${not_repo}" "${output_file}"
not_repo_status=$?
if (( not_repo_status != 0 )); then
  pass "directory without an exact Git repository is rejected"
else
  fail "directory without an exact Git repository is rejected"
fi
assert_contains "$(<"${output_file}")" "git_repo=FAIL" "non-repository reports Git failure"

for protected_branch in main master; do
  protected_repo="${approved_root}/${protected_branch}-repo"
  make_clean_repo "${protected_repo}" "${protected_branch}"
  output_file="${TEST_ROOT}/${protected_branch}.out"
  run_checker "${approved_root}" "${protected_repo}" "${output_file}"
  protected_status=$?
  if (( protected_status != 0 )); then
    pass "${protected_branch} branch is rejected"
  else
    fail "${protected_branch} branch is rejected"
  fi
  assert_contains "$(<"${output_file}")" "branch=FAIL" "${protected_branch} reports branch failure"
done

dirty_repo="${approved_root}/dirty-repo"
make_clean_repo "${dirty_repo}"
print -r -- "uncommitted" > "${dirty_repo}/dirty.txt"
output_file="${TEST_ROOT}/dirty.out"
run_checker "${approved_root}" "${dirty_repo}" "${output_file}"
dirty_status=$?
if (( dirty_status != 0 )); then
  pass "dirty baseline is rejected"
else
  fail "dirty baseline is rejected"
fi
assert_contains "$(<"${output_file}")" "baseline=FAIL" "dirty baseline reports failure"

typeset -a forbidden_names
forbidden_names=(.env id_ed25519 client-private.pem credentials.json)
typeset -i fixture_index=0
for forbidden_name in "${forbidden_names[@]}"; do
  (( fixture_index += 1 ))
  fixture_repo="${approved_root}/fixture-${fixture_index}"
  make_clean_repo "${fixture_repo}"
  print -r -- "not-a-real-secret" > "${fixture_repo}/${forbidden_name}"
  command git -C "${fixture_repo}" add "${forbidden_name}"
  command git -C "${fixture_repo}" commit -q -m "add forbidden fixture"
  output_file="${TEST_ROOT}/fixture-${fixture_index}.out"
  run_checker "${approved_root}" "${fixture_repo}" "${output_file}"
  fixture_status=$?
  if (( fixture_status != 0 )); then
    pass "forbidden fixture ${fixture_index} is rejected"
  else
    fail "forbidden fixture ${fixture_index} is rejected"
  fi
  fixture_output="$(<"${output_file}")"
  assert_contains "${fixture_output}" "sensitive_files=FAIL" "forbidden fixture ${fixture_index} reports sensitive-file failure"
  assert_not_contains "${fixture_output}" "${forbidden_name}" "checker does not print forbidden fixture ${fixture_index} name"
done

marker_repo="${approved_root}/private-key-marker"
make_clean_repo "${marker_repo}"
print -r -- "-----BEGIN PRIVATE KEY-----" > "${marker_repo}/notes.txt"
command git -C "${marker_repo}" add notes.txt
command git -C "${marker_repo}" commit -q -m "add private key marker fixture"
output_file="${TEST_ROOT}/private-key-marker.out"
run_checker "${approved_root}" "${marker_repo}" "${output_file}"
marker_status=$?
if (( marker_status != 0 )); then
  pass "private-key content marker is rejected"
else
  fail "private-key content marker is rejected"
fi
assert_contains "$(<"${output_file}")" "sensitive_files=FAIL" "private-key marker reports sensitive-file failure"

escape_repo="${approved_root}/symlink-escape"
make_clean_repo "${escape_repo}"
ln -s -- /etc/hosts "${escape_repo}/outside-hosts"
command git -C "${escape_repo}" add outside-hosts
command git -C "${escape_repo}" commit -q -m "add symlink escape fixture"
output_file="${TEST_ROOT}/symlink-escape.out"
run_checker "${approved_root}" "${escape_repo}" "${output_file}"
escape_status=$?
if (( escape_status != 0 )); then
  pass "committed in-repository symlink escape is rejected"
else
  fail "committed in-repository symlink escape is rejected"
fi
assert_contains "$(<"${output_file}")" "symlink_entries=FAIL" "symlink escape reports entry failure"

nested_escape_repo="${approved_root}/nested-symlink-escape"
make_clean_repo "${nested_escape_repo}"
mkdir -p -- "${nested_escape_repo}/nested"
ln -s -- /etc/hosts "${nested_escape_repo}/nested/outside-hosts"
command git -C "${nested_escape_repo}" add nested/outside-hosts
command git -C "${nested_escape_repo}" commit -q -m "add nested symlink escape fixture"
output_file="${TEST_ROOT}/nested-symlink-escape.out"
run_checker "${approved_root}" "${nested_escape_repo}" "${output_file}"
nested_escape_status=$?
if (( nested_escape_status != 0 )); then
  pass "nested committed symlink escape is rejected"
else
  fail "nested committed symlink escape is rejected"
fi
assert_contains "$(<"${output_file}")" "symlink_entries=FAIL" "nested symlink escape reports entry failure"

scoped_repo="${approved_root}/scoped-repo"
make_clean_repo "${scoped_repo}"
print -r -- "outside-only" > "${approved_root}/credentials.json"
output_file="${TEST_ROOT}/scoped.out"
run_checker "${approved_root}" "${scoped_repo}" "${output_file}"
scoped_status=$?
assert_status "0" "${scoped_status}" "sensitive-looking file outside repository is not scanned"
assert_contains "$(<"${output_file}")" "sensitive_files=PASS" "repo-only scan reports PASS"

if (( failures > 0 )); then
  print -u2 -r -- "RESULT: FAIL (${failures} assertions)"
  exit 1
fi

print -r -- "RESULT: PASS"
