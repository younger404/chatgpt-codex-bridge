"""Bounded, public-safe managed workspace evidence. No execution authority."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import select
import time
import subprocess

PROTOCOL = 'app-server-rust-v0.106.0'
ALIAS = re.compile(r'[a-z][a-z0-9-]{0,62}')
HEX = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'[0-9a-f]{64}')
# Deliberately conservative: unsafe source remains local, with an explicit marker.
UNSAFE = re.compile(
    r'(?i)(?:cgb2[._-]|\b(?:threadId|jobId|internalThreadId|internalJobId)\b|'
    r'(?<![A-Za-z0-9_:/])/(?!dev/null(?:\W|$))[A-Za-z][A-Za-z0-9_.-]*(?:/|\b)|'
    r'gh[opusr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|'
    r'sk-[A-Za-z0-9_-]{12,}|bearer\s+\S+|'
    r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|'
    r'aws_(?:access_key_id|secret_access_key)\s*[\"\x27]?\s*[:=]|'
    r'(?:password|secret|token|api[_ -]?key|tunnel[_ -]?id)\s*[\"\x27]?\s*[:=]|'
    r'https?://[^\s/@]+:[^\s/@]+@)')
EVIDENCE_FIELDS = {'base', 'head', 'tree', 'files', 'diff', 'artifactState',
                   'candidateDigest', 'checks', 'checksState', 'collectionState'}

EVIDENCE_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': sorted(EVIDENCE_FIELDS),
    'properties': {
        **{k: {'type': ['string','null'], 'pattern': '^[0-9a-f]{40}$'} for k in ('base','head','tree')},
        'candidateDigest': {'type': ['string','null'], 'pattern': '^[0-9a-f]{64}$'},
        'files': {'type': 'array', 'maxItems': 64, 'items': {'type': 'string','maxLength':240}},
        'diff': {'type':'string','maxLength':16000},
        'artifactState': {'enum':['AVAILABLE','WITHHELD','TRUNCATED','NOT_COLLECTED']},
        'collectionState': {'enum':['COLLECTED','NOT_COLLECTED']},
        'checksState': {'enum':['RECORDED','NOT_RUN','WITHHELD']},
        'checks': {'type':'array','maxItems':64,'items': {'type':'object','additionalProperties':False,
            'required':['command','exitCode'], 'properties': {'command':{'type':'string','maxLength':1000},
                                                            'exitCode':{'type':['integer','null']}}}},
    }
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def safe_text(value, forbidden=()):
    return (isinstance(value, str) and not UNSAFE.search(value)
            and not any(item and item in value for item in forbidden)
            and not any(ord(c) < 32 and c not in '\n\r\t' for c in value))


def safe_relative(value):
    return (isinstance(value, str) and 0 < len(value) <= 240
            and re.fullmatch(r'[A-Za-z0-9_. /-]+', value) is not None
            and not value.startswith('/') and all(p not in ('', '.', '..', '.git')
                and p.lower() != '.env' and not p.lower().startswith('.env.')
                for p in value.split('/')) and safe_text(value))


def empty_evidence():
    return dict(base=None, head=None, tree=None, files=[], diff='',
                artifactState='NOT_COLLECTED', candidateDigest=None, checks=[],
                checksState='NOT_RUN', collectionState='NOT_COLLECTED')


def validate_evidence(value, forbidden=()):
    if not isinstance(value, dict) or set(value) != EVIDENCE_FIELDS:
        raise ValueError('invalid evidence fields')
    for key in ('base', 'head', 'tree'):
        if value[key] is not None and (not isinstance(value[key], str) or not HEX.fullmatch(value[key])):
            raise ValueError('invalid git identity')
    if value['candidateDigest'] is not None and (not isinstance(value['candidateDigest'], str)
            or not DIGEST.fullmatch(value['candidateDigest'])):
        raise ValueError('invalid candidate identity')
    if (not isinstance(value['files'], list) or len(value['files']) > 64
            or any(not safe_relative(p) for p in value['files'])):
        raise ValueError('invalid evidence paths')
    if not isinstance(value['diff'], str) or len(value['diff'].encode()) > 16000:
        raise ValueError('invalid evidence artifact')
    if value['artifactState'] not in ('AVAILABLE', 'WITHHELD', 'TRUNCATED', 'NOT_COLLECTED'):
        raise ValueError('invalid artifact state')
    if value['collectionState'] not in ('COLLECTED', 'NOT_COLLECTED'):
        raise ValueError('invalid collection state')
    if value['checksState'] not in ('RECORDED', 'NOT_RUN', 'WITHHELD'):
        raise ValueError('invalid checks state')
    checks = value['checks']
    if not isinstance(checks, list) or len(checks) > 64:
        raise ValueError('invalid command evidence')
    for check in checks:
        if not isinstance(check, dict) or set(check) != {'command', 'exitCode'}:
            raise ValueError('invalid command record')
        if not isinstance(check['command'], str) or len(check['command']) > 1000:
            raise ValueError('invalid command text')
        if check['exitCode'] is not None and type(check['exitCode']) is not int:
            raise ValueError('invalid command exit')
    if not safe_text(json.dumps(value, ensure_ascii=False), forbidden):
        raise ValueError('unsafe evidence')
    return value


def collect_evidence(workspace, base, commands, forbidden=()):
    result = empty_evidence()
    # Check evidence is independent of whether workspace artifacts can be shared.
    for item in commands[:64]:
        command = item.get('command')
        code = item.get('exitCode')
        if (safe_text(command, forbidden) and len(command) <= 1000
                and (code is None or type(code) is int)):
            result['checks'].append(dict(command=command, exitCode=code))
        else:
            result['checksState'] = 'WITHHELD'
    if result['checksState'] != 'WITHHELD' and result['checks']:
        result['checksState'] = 'RECORDED'
    root = Path(workspace)
    if not root.is_absolute() or root.resolve() != root or not HEX.fullmatch(base or ''):
        return validate_evidence(result, forbidden)

    def git(*args):
        proc = subprocess.Popen(['git', '-c', 'core.fsmonitor=false', '-C', str(root), *args],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                env={k: v for k, v in os.environ.items() if not k.startswith('GIT_')})
        output = bytearray()
        deadline = time.monotonic() + 15
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([proc.stdout], [], [], remaining)[0]:
                    raise ValueError('git evidence deadline exceeded')
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > 256000:
                    raise ValueError('git evidence output withheld')
            if proc.wait(timeout=max(0.01, deadline-time.monotonic())):
                raise ValueError('git evidence unavailable')
            return bytes(output)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdout.close()

    try:
        result.update(base=base, head=git('rev-parse', 'HEAD').decode().strip(),
                      tree=git('rev-parse', 'HEAD^{tree}').decode().strip())
        tracked = git('diff', '--name-only', '-z', base, '--').decode().split('\0')
        untracked = git('ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')
        names = sorted(set(filter(None, tracked + untracked)))
        # Bound files before diff. Never read symlink targets, even inside the root.
        if len(names) > 64 or any(not safe_relative(n) for n in names):
            raise ValueError('artifact paths withheld')
        total = 0
        for name in names:
            path = root / name
            if path.resolve() != path:
                raise ValueError('unsafe artifact path')
            if path.exists():
                metadata = path.lstat()
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 64000:
                    raise ValueError('artifact size or type withheld')
                total += metadata.st_size
        if total > 128000:
            raise ValueError('artifact set withheld')
        raw_diff = git('diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--binary', base, '--')
        artifacts = []
        for name in filter(None, untracked):
            fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream:
                data = stream.read(64001)
            if len(data) > 64000 or b'\0' in data:
                raise ValueError('artifact size or type withheld')
            artifacts.append((name, data.decode('utf-8')))
        result['candidateDigest'] = digest([base, result['head'], result['tree'],
                                            raw_diff.hex(), artifacts])
        text = raw_diff.decode('utf-8')
        for name, content in artifacts:
            text += '\n--- /dev/null\n+++ b/' + name + '\n' + ''.join('+' + line + '\n' for line in content.splitlines())
        result['files'] = names
        if b'GIT binary patch' in raw_diff or not safe_text(text, forbidden):
            result['artifactState'] = 'WITHHELD'
        elif len(text.encode()) > 16000:
            result['artifactState'] = 'TRUNCATED'
            # No partial secret-prone fragments. Identity is retained; artifact withheld.
        else:
            result.update(diff=text, artifactState='AVAILABLE')
        result['collectionState'] = 'COLLECTED'
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        result.update(artifactState='WITHHELD', diff='')
    if not safe_text(json.dumps([result['files'], result['diff']], ensure_ascii=False), forbidden):
        result.update(files=[], diff='', artifactState='WITHHELD')
    return validate_evidence(result, forbidden)
