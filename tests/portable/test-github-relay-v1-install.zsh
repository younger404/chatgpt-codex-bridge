#!/bin/zsh
set -euo pipefail
readonly REPO_ROOT="${0:A:h:h:h}"
exec /usr/bin/python3 - "${REPO_ROOT}" <<'PY'
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import sys
import tempfile
from unittest import mock

sys.dont_write_bytecode = True
root = Path(sys.argv[1])
package = root / 'plugins/chatgpt-codex-bridge'
installer = package / 'scripts/install-github-relay-v1-macos.zsh'
assert installer.is_file(), 'dedicated V1 installer is missing'
for name in ('github-issue-relay.py', 'run-github-relay.zsh'):
    assert (package / 'relay' / name).read_bytes() == (root / 'scripts/relay' / name).read_bytes()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def snapshot(home):
    return {str(p.relative_to(home)): (stat.S_IMODE(p.lstat().st_mode),
            hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
            for p in home.rglob('*') if not p.is_symlink()}


with tempfile.TemporaryDirectory(prefix='github-relay-v1-install-') as temporary:
    base = Path(temporary).resolve()
    home = base / 'home'
    workspace = base / 'workspace with spaces'
    home.mkdir(mode=0o700)
    workspace.mkdir()
    codex = base / 'fake-codex'
    codex.write_text('''#!/usr/bin/python3
import os, sys
from pathlib import Path
with (Path(os.environ['HOME'])/'codex-calls').open('a') as f: f.write(repr(sys.argv[1:])+'\\n')
if sys.argv[1:9] != ['exec','--ignore-user-config','--ephemeral','--sandbox','workspace-write','-c','approval_policy="never"','--skip-git-repo-check']:
    raise SystemExit(64)
assert sys.argv[9]=='--cd'
(Path(sys.argv[10])/'workspace-marker').write_text('synthetic')
''')
    codex.chmod(0o700)
    env = dict(os.environ, HOME=str(home), CODEX_HOME=str(home / '.codex'),
               PYTHONDONTWRITEBYTECODE='1', GIT_CONFIG_GLOBAL='/dev/null',
               GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0')
    env.pop('CHATGPT_CODEX_BRIDGE_CONFIG', None)
    env.pop('CHATGPT_CODEX_BRIDGE_STATE_DIR', None)
    env.pop('CHATGPT_CODEX_BRIDGE_MANAGED_REGISTRY', None)

    def run(args, expected=0):
        p = subprocess.run([str(x) for x in args], env=env, capture_output=True, text=True)
        assert p.returncode == expected, (p.returncode, p.stdout, p.stderr)
        return p

    for alias in ('sample-alpha', 'sample-beta'):
        repo = base / alias
        repo.mkdir()
        run(['git', '-C', repo, 'init', '-q', '-b', 'main'])
        run(['git', '-C', repo, '-c', 'user.name=Fixture', '-c',
             'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture', '--allow-empty'])
        run(['git', '-C', repo, 'remote', 'add', 'origin', 'https://github.com/example/' + alias + '.git'])
        run(['/bin/zsh', package / 'scripts/managed-repos.zsh', 'register',
             '--alias', alias, '--repo-path', repo, '--repository-full-name', 'example/' + alias])
    state = home / 'Library/Application Support/chatgpt-codex-bridge'
    registry = state / 'managed-repos.v1.json'
    registry_bytes = registry.read_bytes()
    argv = ['/bin/zsh', installer, '--workspace', workspace, '--codex-bin', codex,
            '--control-repository', 'example/control-private', '--allowed-author', 'fixture-owner',
            '--enable-alias', 'sample-alpha', '--enable-alias', 'sample-beta', '--no-start']
    before = snapshot(home)
    for option in ('--job-state-dir', '--capability-key', '--state', '--unknown'):
        run(argv + [option, str(base / 'caller-selected')], expected=2)
        assert snapshot(home) == before
    for extra in (['--enable-alias', 'sample-alpha'], ['--enable-alias', 'unregistered']):
        run(argv + extra, expected=64)
        assert snapshot(home) == before
    # Each existing-state family rejects before even invoking the policy probe.
    conflicts = [state / 'config.plist', state / 'managed-jobs-v1', state / 'jobs-v4',
                 state / 'github-relay.sqlite3', state / 'capability.key',
                 home / '.local/share/chatgpt-codex-bridge',
                 home / 'Library/LaunchAgents/com.chatgpt-codex-bridge.github-relay.plist']
    for conflict in conflicts:
        conflict.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        conflict.write_bytes(b'preserve')
        captured = snapshot(home)
        assert 'FRESH_INSTALL_REQUIRED' in run(argv, expected=64).stderr
        assert snapshot(home) == captured
        conflict.unlink()
    # Symlink destinations must not redirect writes outside the installation.
    runtime = home / '.local/share/chatgpt-codex-bridge'
    runtime.symlink_to(workspace, target_is_directory=True)
    assert 'FRESH_INSTALL_REQUIRED' in run(argv, expected=64).stderr
    assert not list(workspace.iterdir())
    runtime.unlink()
    result = run(argv)
    assert 'POLICY_SUPPORT=NOT_PROBED' in result.stdout
    assert 'PLIST_DEFAULT_DISABLED=true' in result.stdout
    assert 'LAUNCHD_STATE=NOT_PROBED' in result.stdout
    assert 'SERVICE_STARTED_BY_INSTALLER=false' in result.stdout
    assert 'SERVICE=DISABLED' not in result.stdout
    assert not (home / 'codex-calls').exists()
    config_path = state / 'config.plist'
    config = plistlib.loads(config_path.read_bytes())
    assert config_path.resolve() == config_path and not config_path.is_symlink()
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert config['preset'] == 'managed-repo' and config['sandbox'] == 'workspace-write'
    assert config['approval_policy'] == 'never'
    assert config['relay_control_repository'] == 'example/control-private'
    assert config['relay_allowed_authors'] == ['fixture-owner']
    assert config['relay_enabled_aliases'] == ['sample-alpha', 'sample-beta']
    assert 'relay_branch_prefixes' not in config
    assert Path(config['workspace']) == workspace
    assert registry.read_bytes() == registry_bytes
    store = Path(config['job_state_dir'])
    assert store.parent == state and store.name == 'managed-jobs-v1' and store.resolve() == store
    assert stat.S_IMODE(store.stat().st_mode) == 0o700
    key = store / 'capability.key'
    info = key.lstat()
    assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
    assert info.st_size == 32 and info.st_nlink == 1 and info.st_uid == os.getuid()
    assert {p.name for p in state.iterdir()} == {'config.plist', 'managed-repos.v1.json', 'managed-jobs-v1'}
    run(['/usr/bin/python3', '-I', runtime / 'guard-store-config.py', 'validate', config_path])
    mapping = {
        'bridge/codex-mcp-guard.py': 'bridge/codex-mcp-guard.py',
        'bridge/managed_repo.py': 'bridge/managed_repo.py',
        'bridge/supervision.py': 'bridge/supervision.py',
        'run-guard.zsh': 'scripts/run-guard.zsh',
        'guard-store-config.py': 'scripts/guard-store-config.py',
        'github-relay/github-issue-relay.py': 'relay/github-issue-relay.py',
        'github-relay/run-github-relay.zsh': 'relay/run-github-relay.zsh',
        'github-relay/managed_repo.py': 'bridge/managed_repo.py',
        'github-relay/supervision.py': 'bridge/supervision.py',
        'skills/workspace-new-project/SKILL.md': 'runtime/bootstrap/workspace-new-project/SKILL.md',
        'skills/workspace-new-project/scripts/create_workspace_project.sh':
            'runtime/bootstrap/workspace-new-project/scripts/create_workspace_project.sh',
    }
    assert {str(p.relative_to(runtime)) for p in runtime.rglob('*') if p.is_file()} == set(mapping)
    for relative, source in mapping.items():
        p = runtime / relative
        assert not p.is_symlink() and p.read_bytes() == (package / source).read_bytes()
    agents = home / 'Library/LaunchAgents'
    assert [p.name for p in agents.iterdir()] == ['com.chatgpt-codex-bridge.github-relay.plist']
    agent_path = next(agents.iterdir())
    run(['/usr/bin/plutil', '-lint', agent_path])
    agent = plistlib.loads(agent_path.read_bytes())
    assert agent['ProgramArguments'] == ['/bin/zsh', str(runtime / 'github-relay/run-github-relay.zsh')]
    assert agent['EnvironmentVariables']['HOME'] == str(home)
    assert agent['Disabled'] is True
    assert agent['EnvironmentVariables']['PATH'] == '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'

    with mock.patch.dict(os.environ, env, clear=True):
        relay = load('fixture_relay', runtime / 'github-relay/github-issue-relay.py')
        operator = relay.OperatorConfig.load(config_path)
        assert set(operator.prefixes) == {'sample-alpha', 'sample-beta'}
        assert operator.repository == 'example/control-private'
        # No service/database is created by installation. The test creates this journal offline.
        journal = state / 'github-relay.sqlite3'
        assert not journal.exists()
        db = relay.RelayDatabase(journal, operator)
        try:
            assert db.connection.execute('pragma user_version').fetchone()[0] == 4
            assert db.connection.execute('select scope from relay_scope').fetchone()[0] == operator.scope
            assert not db.active_jobs() and not db.pending_results()
        finally:
            db.close()
        # Installed synthetic Guard only initializes and lists tools; no App Server call.
        client = relay.GuardMcpClient(runtime / 'run-guard.zsh', config_path)
        try:
            assert relay.REQUIRED_TOOLS <= client.start()
        finally:
            client.close()
    assert not (home / 'codex-calls').exists()
    assert not [p for p in store.iterdir() if p.is_dir()]
    captured = snapshot(home)
    assert 'FRESH_INSTALL_REQUIRED' in run(argv, expected=64).stderr
    assert snapshot(home) == captured and registry.read_bytes() == registry_bytes
    # Generic installer keeps its independent explicit-store recovery rejection.
    generic = run(['/bin/zsh', package / 'scripts/install-macos.zsh', '--preset',
                   'managed-repo', '--workspace', workspace, '--no-start'], expected=1)
    assert 'EXPLICIT_STORE_REQUIRES_REVIEWED_RECOVERY' in generic.stderr
    assert snapshot(home) == captured
    # Exercise the equivalent support probe only against the synthetic Codex.
    helper = load('fixture_installer', package / 'scripts/install-github-relay-v1.py')
    with mock.patch.dict(os.environ, env, clear=True):
        helper.policy_probe(codex, workspace, home)
    assert (home / 'codex-calls').is_file()
    # The startup path must stop before installation writes when auth is absent.
    fresh_home = base / 'auth-rejected-home'
    fresh_registry = fresh_home / 'Library/Application Support/chatgpt-codex-bridge/managed-repos.v1.json'
    fresh_registry.parent.mkdir(mode=0o700, parents=True)
    fresh_registry.write_bytes(registry_bytes)
    fresh_registry.chmod(0o600)
    fresh_env = dict(env, HOME=str(fresh_home), CODEX_HOME=str(fresh_home / '.codex'))
    real_run = subprocess.run
    auth_calls = []
    def reject_auth(command, **kwargs):
        if command[0] == 'git':
            return real_run(command, **kwargs)
        if command[0] == 'fixture-gh':
            assert command[1:] == ['auth', 'status', '--hostname', 'github.com']
            assert (fresh_home / 'codex-calls').exists()
            assert {p.name for p in fresh_registry.parent.iterdir()} == {'managed-repos.v1.json'}
            auth_calls.append(command)
            return subprocess.CompletedProcess(command, 1)
        assert command[0] == str(codex), 'unexpected service or network call'
        return real_run(command, **kwargs)
    with mock.patch.dict(os.environ, fresh_env, clear=True), \
         mock.patch.object(helper.shutil, 'which', return_value='fixture-gh'), \
         mock.patch.object(helper.subprocess, 'run', side_effect=reject_auth):
        assert helper.main([str(x) for x in argv[2:-1]]) == 64
    assert len(auth_calls) == 1
    assert not (fresh_home / '.local').exists()
    assert {p.name for p in fresh_registry.parent.iterdir()} == {'managed-repos.v1.json'}
    # no-start permits registry Git reads and the actual static store validator.
    no_start_calls = []
    def static_only(command, **kwargs):
        if command[0] == 'git':
            return real_run(command, **kwargs)
        assert len(command) == 5 and command[1] == '-I'
        assert command[2].endswith('/guard-store-config.py') and command[3] == 'validate'
        no_start_calls.append(command)
        return real_run(command, **kwargs)
    with mock.patch.dict(os.environ, fresh_env, clear=True), \
         mock.patch.object(helper.subprocess, 'run', side_effect=static_only):
        assert helper.main([str(x) for x in argv[2:]]) == 0
    assert len(no_start_calls) == 1
    # Exercise the real installation path with synthetic activation/auth only.
    for failure in ('bootstrap', 'enable', 'disable'):
        activation_home = base / ('activation-fails-' + failure)
        activation_state = activation_home / 'Library/Application Support/chatgpt-codex-bridge'
        activation_state.mkdir(mode=0o700, parents=True)
        activation_registry = activation_state / 'managed-repos.v1.json'
        activation_registry.write_bytes(registry_bytes)
        activation_registry.chmod(0o600)
        activation_env = dict(env, HOME=str(activation_home), CODEX_HOME=str(activation_home / '.codex'))
        activation_calls = []
        def activation_run(command, **kwargs):
            if command[0] == 'git':
                return real_run(command, **kwargs)
            if len(command) == 5 and command[2].endswith('/guard-store-config.py'):
                assert command[1] == '-I' and command[3] == 'validate'
                return real_run(command, **kwargs)
            if command[0] == 'fixture-gh':
                assert command[1:] == ['auth', 'status', '--hostname', 'github.com']
                return subprocess.CompletedProcess(command, 0)
            assert command[0] == '/bin/launchctl', 'unexpected model or GitHub work'
            assert command[1] in ('enable', 'bootstrap', 'disable')
            activation_calls.append(command)
            failed_calls = {'bootstrap', 'disable'} if failure == 'disable' else {failure}
            if command[1] in failed_calls:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)
        with mock.patch.dict(os.environ, activation_env, clear=True), \
             mock.patch.object(helper, 'policy_probe') as probe, \
             mock.patch.object(helper.shutil, 'which', return_value='fixture-gh'), \
             mock.patch.object(helper.subprocess, 'run', side_effect=activation_run):
            assert helper.main([str(x) for x in argv[2:-1]]) == 64
            expected = ['enable', 'disable'] if failure == 'enable' else ['enable', 'bootstrap', 'disable']
            assert [c[1] for c in activation_calls] == expected, 'missing activation disable rollback'
            assert activation_calls[-1][2] == activation_calls[0][2] == 'gui/' + str(os.getuid()) + '/' + helper.LABEL
            activation_plist = activation_home / 'Library/LaunchAgents' / (helper.LABEL + '.plist')
            assert plistlib.loads(activation_plist.read_bytes())['Disabled'] is True
            assert (activation_state / 'config.plist').is_file()
            activation_store = activation_state / 'managed-jobs-v1'
            assert [p.name for p in activation_store.iterdir()] == ['capability.key']
            assert (activation_home / '.local/share/chatgpt-codex-bridge/github-relay/github-issue-relay.py').is_file()
            assert not (activation_state / 'github-relay.sqlite3').exists()
            assert not (activation_home / 'codex-calls').exists()
            captured_partial = snapshot(activation_home)
            captured_calls = list(activation_calls)
            assert helper.main([str(x) for x in argv[2:-1]]) == 64
            assert snapshot(activation_home) == captured_partial
            assert activation_calls == captured_calls and probe.call_count == 1
        print('Activation failure rollback: PASS (' + failure + ')')
    codex.write_text('''#!/usr/bin/python3
from pathlib import Path
import sys
(Path(sys.argv[10])/'workspace-marker').write_text('synthetic')
outside = sys.argv[11].split('attempt to create ', 1)[1].split('. Do not request', 1)[0]
Path(outside).write_text('escaped')
''')
    with mock.patch.dict(os.environ, env, clear=True):
        try:
            helper.policy_probe(codex, workspace, home)
        except ValueError as error:
            assert str(error) == 'MANAGED_POLICY_SUPPORT_REJECTED'
        else:
            raise AssertionError('outside-workspace write was accepted')
    codex.write_text('#!/bin/zsh\nexit 1\n')
    with mock.patch.dict(os.environ, env, clear=True):
        try:
            helper.policy_probe(codex, workspace, home)
        except ValueError as error:
            assert str(error) == 'MANAGED_POLICY_SUPPORT_REJECTED'
        else:
            raise AssertionError('unsupported policy was accepted')
print('GitHub Relay V1 clean install: PASS (offline; no-start policy support NOT_PROBED)')
PY
