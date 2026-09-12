"""Fresh-only managed GitHub Relay installation; no existing-state recovery."""
import argparse
import importlib.util
import os
from pathlib import Path
import plistlib
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
PACKAGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACKAGE / 'bridge'))
from managed_repo import Registry, ManagedRepoError, ALIAS_PATTERN, FULL_NAME_PATTERN

LABEL = 'com.chatgpt-codex-bridge.github-relay'
BOUNDED_PATH = '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'


def require(condition, category):
    if not condition:
        raise ValueError(category)


def canonical(raw):
    path = Path(raw)
    require(path.is_absolute() and str(path) == raw and path.resolve() == path
            and not any(ord(c) < 32 or ord(c) == 127 for c in raw),
            'INSTALL_INPUT_REJECTED')
    return path


def safe_ancestors(path, home):
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                    and not info.st_mode & 0o022 and item.resolve() == item,
                    'FRESH_INSTALL_REQUIRED')
        if item == home:
            return
    raise ValueError('INSTALL_INPUT_REJECTED')


def fresh_paths(home, state, runtime, logs, agents):
    for path in (state, runtime.parent, logs.parent, agents):
        safe_ancestors(path, home)
    require(not runtime.exists() and not runtime.is_symlink()
            and not logs.exists() and not logs.is_symlink(), 'FRESH_INSTALL_REQUIRED')
    if state.exists():
        require({p.name for p in state.iterdir()} <= {'managed-repos.v1.json'},
                'FRESH_INSTALL_REQUIRED')
    if agents.exists():
        require(not list(agents.glob('com.chatgpt-codex-bridge*.plist')),
                'FRESH_INSTALL_REQUIRED')


def policy_probe(codex, workspace, home):
    # Same exec flags and inside/outside write test as verify_managed_policy_support.
    with tempfile.TemporaryDirectory(prefix='.bridge-policy-probe.', dir=workspace) as probe:
        with tempfile.TemporaryDirectory(prefix='.bridge-policy-outside.', dir=home) as outside:
            marker = Path(outside) / 'outside-marker'
            result = subprocess.run([
                str(codex), 'exec', '--ignore-user-config', '--ephemeral',
                '--sandbox', 'workspace-write', '-c', 'approval_policy="never"',
                '--skip-git-repo-check', '--cd', probe,
                'Use the shell to create ./workspace-marker, then attempt to create '
                + str(marker) + '. Do not request approval.',
            ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=120)
            require(result.returncode == 0 and (Path(probe) / 'workspace-marker').is_file()
                    and not marker.exists(), 'MANAGED_POLICY_SUPPORT_REJECTED')


def publish_new(path, data, mode):
    # Link an already complete private file without ever replacing an existing target.
    fd, name = tempfile.mkstemp(prefix='.install-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--codex-bin', required=True)
    parser.add_argument('--control-repository', required=True)
    parser.add_argument('--allowed-author', required=True)
    parser.add_argument('--enable-alias', action='append', required=True)
    parser.add_argument('--no-start', action='store_true')
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        home = canonical(os.environ['HOME'])
        workspace = canonical(args.workspace)
        codex = canonical(args.codex_bin)
        require(home.is_dir() and workspace.is_dir() and codex.is_file()
                and os.access(codex, os.X_OK), 'INSTALL_INPUT_REJECTED')
        require(FULL_NAME_PATTERN.fullmatch(args.control_repository)
                and re.fullmatch(r'[A-Za-z0-9-]{1,39}', args.allowed_author)
                and len(set(args.enable_alias)) == len(args.enable_alias)
                and all(ALIAS_PATTERN.fullmatch(a) for a in args.enable_alias),
                'INSTALL_INPUT_REJECTED')
        state = home / 'Library/Application Support/chatgpt-codex-bridge'
        runtime = home / '.local/share/chatgpt-codex-bridge'
        logs = home / 'Library/Logs/chatgpt-codex-bridge'
        agents = home / 'Library/LaunchAgents'
        store = state / 'managed-jobs-v1'
        config_path = state / 'config.plist'
        registry = state / 'managed-repos.v1.json'
        fresh_paths(home, state, runtime, logs, agents)
        for path in (state, runtime, logs, agents):
            require(path != workspace and path not in workspace.parents
                    and workspace not in path.parents, 'INSTALL_INPUT_REJECTED')
        require(registry.is_file() and registry.stat().st_uid == os.getuid()
                and registry.stat().st_nlink == 1, 'REGISTRY_REJECTED')
        document = Registry(registry).load(verify_live=True)
        entries = {entry['alias']: entry for entry in document['repos']}
        require(all(a in entries for a in args.enable_alias), 'REGISTRY_REJECTED')

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
            'skills/workspace-new-project/SKILL.md':
                'runtime/bootstrap/workspace-new-project/SKILL.md',
            'skills/workspace-new-project/scripts/create_workspace_project.sh':
                'runtime/bootstrap/workspace-new-project/scripts/create_workspace_project.sh',
        }
        files = {}
        for target, relative in mapping.items():
            source = PACKAGE / relative
            require(source.is_file() and source.resolve() == source, 'PACKAGE_REJECTED')
            files[target] = source.read_bytes()
        if not args.no_start:
            policy_probe(codex, workspace, home)
            gh = shutil.which('gh', path=BOUNDED_PATH)
            require(gh is not None, 'GITHUB_AUTH_REQUIRED')
            result = subprocess.run([gh, 'auth', 'status', '--hostname', 'github.com'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=30)
            require(result.returncode == 0, 'GITHUB_AUTH_REQUIRED')

        # Recheck after the external probe; reserve the new store exclusively.
        fresh_paths(home, state, runtime, logs, agents)
        require(Registry(registry).load(verify_live=True) == document, 'REGISTRY_REJECTED')
        store.mkdir(mode=0o700)
        runtime.mkdir(mode=0o700, parents=True)
        logs.mkdir(mode=0o700, parents=True)
        agents.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(store / 'capability.key', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(secrets.token_bytes(32))
        for relative, data in files.items():
            target = runtime / relative
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            publish_new(target, data, 0o700 if target.suffix in ('.sh', '.zsh') else 0o600)
        config = dict(workspace=str(workspace), python_bin=str(Path(sys.executable).resolve()),
                      codex_bin=str(codex), preset='managed-repo', sandbox='workspace-write',
                      approval_policy='never', runtime_guard=str(runtime / 'bridge/codex-mcp-guard.py'),
                      runtime_managed_repo=str(runtime / 'bridge/managed_repo.py'),
                      runtime_wrapper=str(runtime / 'run-guard.zsh'), managed_registry=str(registry),
                      workspace_new_project_skill=str(runtime / 'skills/workspace-new-project/SKILL.md'),
                      job_state_dir=str(store), relay_control_repository=args.control_repository,
                      relay_allowed_authors=[args.allowed_author], relay_enabled_aliases=args.enable_alias)
        publish_new(config_path, plistlib.dumps(config), 0o600)
        checked = subprocess.run([sys.executable, '-I', str(runtime / 'guard-store-config.py'),
                                  'validate', str(config_path)], capture_output=True)
        require(checked.returncode == 0, 'GENERATED_CONFIG_REJECTED')
        spec = importlib.util.spec_from_file_location('installed_relay', runtime / 'github-relay/github-issue-relay.py')
        relay = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(relay)
        relay.OperatorConfig.load(config_path)

        plist = dict(Label=LABEL, ProgramArguments=['/bin/zsh', str(runtime / 'github-relay/run-github-relay.zsh')],
                     EnvironmentVariables=dict(HOME=str(home), PATH=BOUNDED_PATH), RunAtLoad=True,
                     Disabled=True, KeepAlive=dict(SuccessfulExit=False), ThrottleInterval=15,
                     ProcessType='Background', StandardOutPath=str(logs / 'github-relay.stdout.log'),
                     StandardErrorPath=str(logs / 'github-relay.stderr.log'))
        target_plist = agents / (LABEL + '.plist')
        publish_new(target_plist, plistlib.dumps(plist), 0o600)
        if args.no_start:
            print('GITHUB_RELAY_V1_CONFIGURED POLICY_SUPPORT=NOT_PROBED '
                  'PLIST_DEFAULT_DISABLED=true LAUNCHD_STATE=NOT_PROBED '
                  'SERVICE_STARTED_BY_INSTALLER=false')
        else:
            domain = 'gui/' + str(os.getuid())
            service_target = domain + '/' + LABEL
            try:
                subprocess.run(['/bin/launchctl', 'enable', service_target], check=True)
                subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(target_plist)], check=True)
            except (OSError, subprocess.SubprocessError):
                try:
                    subprocess.run(['/bin/launchctl', 'disable', service_target], check=True)
                except (OSError, subprocess.SubprocessError):
                    print('ACTIVATION_DISABLE_ROLLBACK_FAILED', file=sys.stderr)
                raise
            print('GITHUB_RELAY_V1_STARTED POLICY_SUPPORT=PASS')
        return 0
    except FileExistsError:
        print('FRESH_INSTALL_REQUIRED', file=sys.stderr)
    except (ValueError, ManagedRepoError, OSError, KeyError, subprocess.SubprocessError) as error:
        known = {'INSTALL_INPUT_REJECTED', 'FRESH_INSTALL_REQUIRED', 'REGISTRY_REJECTED',
                 'PACKAGE_REJECTED', 'MANAGED_POLICY_SUPPORT_REJECTED',
                 'GITHUB_AUTH_REQUIRED', 'GENERATED_CONFIG_REJECTED'}
        print(str(error) if str(error) in known else 'INSTALL_REJECTED', file=sys.stderr)
    return 64


if __name__ == '__main__':
    raise SystemExit(main())
