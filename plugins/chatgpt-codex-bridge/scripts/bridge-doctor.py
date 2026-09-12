"""Explicit operator modes for the existing doctor. No default installed inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import sys
from xml.parsers.expat import ExpatError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_observation import MacProcessReader, observe_window, validate_contract


SOURCE_FILES = (
    'scripts/relay/github-issue-relay.py',
    'scripts/relay/run-github-relay.zsh',
    'scripts/bridge/codex-mcp-guard.py',
    'scripts/bridge/managed_repo.py',
    'scripts/bridge/supervision.py',
    'plugins/chatgpt-codex-bridge/scripts/run-guard.zsh',
    'plugins/chatgpt-codex-bridge/scripts/bridge-doctor.py',
    'plugins/chatgpt-codex-bridge/scripts/process_observation.py',
)
CONFIG_PATH_FIELDS = ('python_bin', 'codex_bin', 'runtime_guard',
                      'runtime_managed_repo', 'runtime_wrapper', 'managed_registry', 'job_state_dir')


def static_checks(config_path, source_root, expected_path=None):
    checks = []

    def add(field, result):
        checks.append(dict(field=field, result=result))

    config = {}
    try:
        with open(config_path, 'rb') as source:
            config = plistlib.load(source)
        if not isinstance(config, dict):
            raise ValueError('config must be a mapping')
        add('config', 'READ')
    except FileNotFoundError:
        add('config', 'MISSING')
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException, ExpatError):
        config = {}
        add('config', 'INVALID')
    for field in CONFIG_PATH_FIELDS:
        value = config.get(field)
        add(field, 'MISSING' if value is None else
            'VALID' if isinstance(value, str) and os.path.isabs(value) else 'INVALID')
    for field, expected in (('preset', 'managed-repo'), ('sandbox', 'workspace-write'),
                            ('approval_policy', 'never')):
        value = config.get(field)
        add(field, 'MISSING' if value is None else 'VALID' if value == expected else 'INVALID')

    for field in ('relay_control_repository', 'relay_allowed_authors', 'relay_enabled_aliases'):
        value = config.get(field)
        valid = False
        if field == 'relay_control_repository':
            valid = isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value) is not None
        elif isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            pattern = r'[a-z][a-z0-9-]{0,62}' if field == 'relay_enabled_aliases' else r'[A-Za-z0-9-]{1,39}'
            valid = len(set(value)) == len(value) and all(re.fullmatch(pattern, v) for v in value)
        add(field, 'MISSING' if value is None else 'VALID' if valid else 'INVALID')

    # Config-referenced paths are NEVER opened, resolved, executed or hashed.
    expected = {}
    if expected_path is not None:
        try:
            with open(expected_path, encoding='utf-8') as source:
                expected = json.load(source)
            if not isinstance(expected, dict) or any(
                    key not in SOURCE_FILES or not isinstance(value, str)
                    or not re.fullmatch(r'[0-9a-f]{64}', value) for key, value in expected.items()):
                raise ValueError('invalid digest mapping')
            add('expected_digests', 'READ')
        except (OSError, ValueError, TypeError):
            expected = {}
            add('expected_digests', 'INVALID')
    root = Path(source_root).resolve()
    for relative in SOURCE_FILES:
        path = root / relative
        try:
            # No source symlink can redirect this mode into an installed store.
            if path.resolve() != path or not path.is_file():
                add(relative, 'MISSING' if not path.exists() else 'INVALID')
                continue
            data = path.read_bytes()
        except OSError:
            add(relative, 'UNREADABLE')
            continue
        add(relative, 'PRESENT')
        digest = expected.get(relative)
        add(relative + ':digest', 'NOT_COLLECTED' if digest is None else
            'MATCH' if hashlib.sha256(data).hexdigest() == digest else 'DRIFT')
    failed = any(item['result'] in ('MISSING', 'INVALID', 'UNREADABLE', 'DRIFT') for item in checks)
    return dict(result='STATIC_CHECKS_FAILED' if failed else 'STATIC_CHECKS_PASSED',
                runtime='NOT_RUN', live_identity='NOT_COLLECTED', checks=checks)


def write_private(path, report):
    # Exclusive creation: no chmod/replace of existing records, no stdout fallback.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as target:
        json.dump(report, target, indent=2, sort_keys=True)
        target.write('\n')


def observation(contract_path, output_path):
    report = dict(result='INPUT_ERROR', complete=False, samples=[], checks=[],
                  target_exit_status=None, cleanup_exit_status=None)
    try:
        with open(contract_path, encoding='utf-8') as source:
            contract = json.load(source)
        report['input'] = contract
        validate_contract(contract)
        reader = MacProcessReader()
        report = dict(observe_window(contract, reader), input=contract)
    except Exception as exc:
        report['error'] = dict(exception_type=type(exc).__name__, exception=str(exc),
                              errno=getattr(exc, 'errno', None))
        report['result'] = 'INPUT_ERROR' if isinstance(exc, (ValueError, TypeError, KeyError)) else 'READ_ERROR'
    recording = 'SAVED'
    try:
        write_private(output_path, report)
    except Exception:
        recording = 'FAILED'
        print('PRIVATE_RECORD_WRITE_FAILED', file=sys.stderr)
    # Never print raw paths, PID, argv, exception, input or native metadata.
    public = dict(result=report['result'] if recording == 'SAVED' else 'PRIVATE_RECORD_WRITE_FAILED',
                  observation_result=report['result'],
                  complete=report['complete'] and recording == 'SAVED', recording=recording,
                  complete_sample_count=sum(s['complete'] for s in report['samples']),
                  partial_sample_count=sum(not s['complete'] for s in report['samples']))
    print(json.dumps(public, sort_keys=True))
    return 0 if report['complete'] and recording == 'SAVED' else 1


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse messages can contain private option values.
        self.print_usage(sys.stderr)
        self.exit(2, 'DOCTOR_ARGUMENTS_INVALID\n')


def main():
    parser = SafeParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--static', action='store_true')
    mode.add_argument('--observe', action='store_true')
    parser.add_argument('--config')
    parser.add_argument('--source-root')
    parser.add_argument('--expected-digests')
    parser.add_argument('--contract')
    parser.add_argument('--private-output')
    args = parser.parse_args()
    if args.static:
        if not args.config or not args.source_root or args.contract or args.private_output:
            parser.error('static inputs required')
        result = static_checks(args.config, args.source_root, args.expected_digests)
        print(json.dumps(result, sort_keys=True))
        return 0 if result['result'] == 'STATIC_CHECKS_PASSED' else 1
    if not args.contract or not args.private_output or args.config or args.source_root or args.expected_digests:
        parser.error('observation inputs required')
    return observation(args.contract, args.private_output)


if __name__ == '__main__':
    raise SystemExit(main())
