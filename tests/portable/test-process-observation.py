"""Offline COMPONENT-01 regressions; system smoke is opt-in and owns its child."""
import contextlib
import ctypes
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'plugins/chatgpt-codex-bridge/scripts'
sys.path.insert(0, str(SCRIPTS))
import process_observation as observer
spec = importlib.util.spec_from_file_location('doctor', SCRIPTS / 'bridge-doctor.py')
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


class Clock:
    def __init__(self):
        self.now = 100.0
        self.waits = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class FakeReader:
    def __init__(self, contract, fail=None, error=errno.EIO, starting=False):
        self.contract = contract
        self.fail = fail
        self.error = error
        self.starting = starting
        self.calls = 0
        self.independent_calls = []

    def info(self, pid):
        self.calls += 1
        detail = dict(operation='proc_pidinfo', actual_length=136, expected_length=136, errno=0)
        if self.calls == self.fail:
            detail.update(actual_length=0, errno=self.error)
            raise observer.ReadFailure(detail)
        return dict(pid=pid, ppid=self.contract['ppid'], uid=self.contract['uid'], pgid=pid,
                    start_sec=10, start_usec=20, status=2), detail

    def executable(self, pid):
        role = 'launcher' if self.starting else 'interpreter'
        return self.contract['files'][role]['path'], dict(errno=0)

    def argv(self, pid):
        files = self.contract['files']
        args = ([files['launcher']['path'], files['runner']['path']] if self.starting else
                [files['interpreter']['path'], files['application']['path'], '--watch'])
        return dict(kernel_exec_path=args[0], argv=args), dict(errno=0)

    def independent(self, pid, remaining):
        self.independent_calls.append(remaining)
        return [self.contract['files'][r]['path'] for r in ('interpreter', 'framework')], dict(returncode=0)


class ObservationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bridge-component-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.clock = Clock()
        self.contract = dict(pid=111, uid=501, ppid=1, label='com.example.synthetic',
                             started_monotonic=100.0, files={})
        for role in observer.FILE_ROLES:
            path = self.root / role
            path.write_text('synthetic ' + role)
            self.contract['files'][role] = dict(path=str(path))
        files = self.contract['files']
        Path(files['plist']['path']).write_bytes(plistlib.dumps(dict(
            Label=self.contract['label'], ProgramArguments=[files[r]['path'] for r in ('launcher', 'runner')])))
        for value in files.values():
            value['sha256'] = hashlib.sha256(Path(value['path']).read_bytes()).hexdigest()
        observer.validate_contract(self.contract)

    def run_window(self, reader):
        return observer.observe_window(self.contract, reader, self.clock, self.clock.sleep)

    def test_before_failure_keeps_native_metadata_and_not_run(self):
        report = self.run_window(FakeReader(self.contract, fail=1))
        self.assertEqual(report['result'], 'READ_ERROR')
        sample = report['samples'][0]
        self.assertFalse(sample['complete'])
        self.assertEqual(sample['failed_step'], 'before')
        self.assertEqual(sample['not_run_steps'], ['executable', 'argv', 'after'])
        detail = sample['steps'][0]['detail']
        self.assertEqual((detail['actual_length'], detail['expected_length'], detail['errno']), (0, 136, errno.EIO))
        self.assertTrue(sample['steps'][0]['at'])
        self.assertIsNone(report['target_exit_status'])

    def test_after_failure_keeps_successful_local_reads(self):
        report = self.run_window(FakeReader(self.contract, fail=2))
        sample = report['samples'][0]
        self.assertEqual(sample['failed_step'], 'after')
        self.assertEqual([s['result'] for s in sample['steps']], ['READ', 'READ', 'READ', 'FAILED'])
        self.assertEqual(sample['not_run_steps'], [])
        self.assertEqual(sample['steps'][3]['detail']['expected_length'], 136)
        self.assertFalse(report['complete'])

    def test_actual_errno_classification_and_unknown_no_retry(self):
        for error, expected in ((errno.EPERM, 'PERMISSION_DENIED'), (errno.ESRCH, 'PROCESS_EXITED'),
                                (0, 'READ_ERROR'), (None, 'READ_ERROR')):
            with self.subTest(error=error):
                reader = FakeReader(self.contract, fail=1, error=error)
                report = self.run_window(reader)
                self.assertEqual(report['result'], expected)
                self.assertEqual(reader.calls, 1)
                self.assertFalse(report['complete'])
                self.assertIsNone(report['cleanup_exit_status'])

    def test_unavailable_exception_errno_stays_null_and_retains_steps(self):
        reader = FakeReader(self.contract)
        with patch.object(reader, 'argv', side_effect=ValueError('synthetic private detail')):
            report = self.run_window(reader)
        sample = report['samples'][0]
        self.assertEqual(sample['state'], 'READ_ERROR')
        self.assertEqual(sample['failed_step'], 'argv')
        self.assertIsNone(sample['steps'][2]['detail']['errno'])
        self.assertEqual(sample['steps'][2]['detail']['exception_type'], 'ValueError')

    def test_complete_requires_independent_and_final_instance_reads(self):
        reader = FakeReader(self.contract)
        report = self.run_window(reader)
        self.assertTrue(report['complete'])
        self.assertEqual(reader.calls, 4)
        self.assertEqual(len(reader.independent_calls), 1)
        self.assertEqual([s['complete'] for s in report['samples']], [False, True])

    def test_changed_instance_after_and_across_transition_fail(self):
        reader = FakeReader(self.contract)
        original = reader.info
        def changed(pid):
            value, detail = original(pid)
            if reader.calls >= 2:
                value['start_usec'] += 1
            return value, detail
        with patch.object(reader, 'info', side_effect=changed):
            self.assertEqual(self.run_window(reader)['result'], 'IDENTITY_CONFLICT')
        reader = FakeReader(self.contract, starting=True)
        original = reader.info
        def replaced(pid):
            value, detail = original(pid)
            if reader.calls >= 3:
                value['start_sec'] += 1
            return value, detail
        with patch.object(reader, 'info', side_effect=replaced):
            self.assertEqual(self.run_window(reader)['result'], 'IDENTITY_CONFLICT')

    def test_wrong_argv_is_conflict_not_starting(self):
        reader = FakeReader(self.contract)
        with patch.object(reader, 'argv', return_value=(dict(kernel_exec_path='wrong', argv=['wrong']), {})):
            report = self.run_window(reader)
        self.assertEqual(report['result'], 'IDENTITY_CONFLICT')
        self.assertEqual(self.clock.waits, [])

    def test_missing_framework_and_failed_final_read_cannot_pass(self):
        reader = FakeReader(self.contract)
        with patch.object(reader, 'independent', return_value=([], dict(returncode=0))):
            self.assertEqual(self.run_window(reader)['result'], 'IDENTITY_CONFLICT')
        report = self.run_window(FakeReader(self.contract, fail=4))
        self.assertEqual(report['result'], 'READ_ERROR')
        self.assertEqual(report['samples'][-1]['failed_step'], 'after')
        self.assertFalse(any(s['complete'] for s in report['samples']))

    def test_static_launcher_mismatch_prevents_process_reads(self):
        Path(self.contract['files']['runner']['path']).write_text('changed')
        reader = FakeReader(self.contract)
        report = self.run_window(reader)
        self.assertEqual(report['result'], 'IDENTITY_CONFLICT')
        self.assertEqual(reader.calls, 0)

    def test_fixed_deadline_only_retries_proven_starting(self):
        reader = FakeReader(self.contract, starting=True)
        report = self.run_window(reader)
        self.assertEqual(report['result'], 'TIMEOUT')
        self.assertEqual(report['deadline'], 115.0)
        self.assertLessEqual(self.clock.now, 115.0)
        self.assertAlmostEqual(sum(self.clock.waits), 15.0)
        self.assertFalse(report['complete'])

    def test_expired_start_and_slow_read_do_not_extend_window(self):
        self.clock.now = 115
        reader = FakeReader(self.contract)
        self.assertEqual(self.run_window(reader)['result'], 'TIMEOUT')
        self.assertEqual(reader.calls, 0)
        self.clock.now = 114.9
        original = reader.executable
        def slow(pid):
            self.clock.now = 115
            return original(pid)
        with patch.object(reader, 'executable', side_effect=slow):
            report = self.run_window(reader)
        self.assertEqual(report['result'], 'TIMEOUT')
        self.assertEqual(reader.calls, 1)
        self.assertEqual(reader.independent_calls, [])
        self.assertEqual(self.clock.waits, [])

    def test_independent_uses_remaining_window_and_drains_diagnostic(self):
        reader = FakeReader(self.contract)
        self.clock.now = 114
        def timed(pid, remaining):
            self.assertEqual(remaining, 1)
            raise observer.ReadFailure(dict(timeout=True, errno=None, returncode=None, stderr='synthetic'))
        with patch.object(reader, 'independent', side_effect=timed):
            report = self.run_window(reader)
        self.assertEqual(report['result'], 'TIMEOUT')
        self.assertEqual(report['checks'][-1]['detail']['stderr'], 'synthetic')
        native = observer.MacProcessReader.__new__(observer.MacProcessReader)
        with patch('process_observation.subprocess.run', return_value=SimpleNamespace(
                returncode=7, stdout='private stdout', stderr='private stderr')) as call:
            with self.assertRaises(observer.ReadFailure) as error:
                native.independent(111, 0.3)
        self.assertEqual(error.exception.detail['returncode'], 7)
        self.assertTrue(call.call_args.kwargs['capture_output'])
        self.assertEqual(call.call_args.kwargs['timeout'], 0.3)

    def test_ctypes_errno_is_captured_immediately_without_stale_value(self):
        native = observer.MacProcessReader.__new__(observer.MacProcessReader)
        native.lib = SimpleNamespace(proc_pidinfo=lambda *args: 0)
        ctypes.set_errno(errno.EPERM)
        with self.assertRaises(observer.ReadFailure) as error:
            native.info(111)
        self.assertEqual(error.exception.detail['errno'], 0)
        self.assertEqual(error.exception.detail['expected_length'], ctypes.sizeof(observer.BsdInfo))
        native.lib.proc_pidinfo = lambda *args: ctypes.sizeof(observer.BsdInfo) - 1
        with self.assertRaises(observer.ReadFailure) as short:
            native.info(111)
        self.assertEqual(short.exception.detail['actual_length'], ctypes.sizeof(observer.BsdInfo) - 1)
        self.assertEqual(observer.classify(short.exception.detail), 'READ_ERROR')
        def denied(*args):
            ctypes.set_errno(errno.EACCES)
            return 0
        native.lib.proc_pidinfo = denied
        with self.assertRaises(observer.ReadFailure) as error:
            native.info(111)
        self.assertEqual(error.exception.detail['errno'], errno.EACCES)
        with patch.object(native.lib, 'proc_pidinfo', side_effect=RuntimeError('synthetic binding failure')):
            with self.assertRaises(observer.ReadFailure) as error:
                native.info(111)
        self.assertIsNone(error.exception.detail['actual_length'])
        self.assertIsNone(error.exception.detail['errno'])
        self.assertEqual(error.exception.detail['expected_length'], ctypes.sizeof(observer.BsdInfo))

    def test_doctor_observe_calls_shared_reader_and_saves_private_failure(self):
        contract = self.root / 'input.json'
        contract.write_text(json.dumps(self.contract))
        output = self.root / 'private.json'
        capture = io.StringIO()
        original = observer.observe_window
        def bounded(value, reader):
            return original(value, reader, self.clock, self.clock.sleep)
        with patch.object(doctor, 'MacProcessReader', return_value=FakeReader(self.contract, fail=2)), \
                patch.object(doctor, 'observe_window', side_effect=bounded), contextlib.redirect_stdout(capture):
            code = doctor.observation(contract, output)
        self.assertEqual(code, 1)
        public = json.loads(capture.getvalue())
        private = json.loads(output.read_text())
        self.assertEqual(public['result'], 'READ_ERROR')
        self.assertNotIn(str(self.root), capture.getvalue())
        self.assertNotIn('errno', capture.getvalue())
        self.assertEqual(private['samples'][0]['failed_step'], 'after')
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        saved = output.read_bytes()
        stderr = io.StringIO()
        with patch.object(doctor, 'MacProcessReader', return_value=FakeReader(self.contract, fail=1)), \
                patch.object(doctor, 'observe_window', side_effect=bounded), \
                contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(stderr):
            code = doctor.observation(contract, output)
        self.assertEqual(code, 1)
        self.assertEqual(output.read_bytes(), saved)
        self.assertEqual(json.loads(stdout.getvalue())['observation_result'], 'READ_ERROR')
        self.assertEqual(json.loads(stdout.getvalue())['result'], 'PRIVATE_RECORD_WRITE_FAILED')
        self.assertEqual(json.loads(stdout.getvalue())['recording'], 'FAILED')
        self.assertEqual(stderr.getvalue(), 'PRIVATE_RECORD_WRITE_FAILED\n')
        with patch.object(doctor, 'MacProcessReader', return_value=FakeReader(self.contract)), \
                patch.object(doctor, 'observe_window', side_effect=bounded), \
                contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
            code = doctor.observation(contract, output)
        self.assertEqual(code, 1)
        public = json.loads(stdout.getvalue())
        self.assertEqual(public['observation_result'], 'COMPLETE')
        self.assertEqual(public['result'], 'PRIVATE_RECORD_WRITE_FAILED')
        self.assertFalse(public['complete'])


class StaticCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bridge-static-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / 'input.plist'
        self.source = self.root / 'source'
        self.source.mkdir()
        self.config.write_bytes(plistlib.dumps({}))
        self.env = dict(HOME=str(self.root / 'absent-home'), PATH='/usr/bin:/bin:/usr/sbin:/sbin',
                        CHATGPT_CODEX_BRIDGE_STATE_DIR=str(self.root / 'absent-state'))

    def run_cli(self, *args):
        return subprocess.run(['/bin/zsh', str(SCRIPTS / 'doctor.zsh'), *args], env=self.env,
                              text=True, capture_output=True, timeout=10)

    def static(self, *args):
        return self.run_cli('--static', '--config', str(self.config), '--source-root', str(self.source), *args)

    def prepare_valid(self):
        # Referenced files are deliberately FIFOs: opening them would block. No
        # executable/registry/version/help check may touch any of these paths.
        config = dict(preset='managed-repo', sandbox='workspace-write', approval_policy='never',
                      relay_control_repository='example/control', relay_allowed_authors=['fixture-owner'],
                      relay_enabled_aliases=['sample-alpha', 'sample-beta'])
        for field in doctor.CONFIG_PATH_FIELDS:
            path = self.root / field
            os.mkfifo(path)
            config[field] = str(path)
        self.config.write_bytes(plistlib.dumps(config))
        for relative in doctor.SOURCE_FILES:
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic source; never executed\n')

    def test_cli_aggregates_missing_without_home_fallback(self):
        result = self.static()
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        missing = {x['field'] for x in data['checks'] if x['result'] == 'MISSING'}
        self.assertTrue(set(doctor.CONFIG_PATH_FIELDS).issubset(missing))
        self.assertTrue(set(doctor.SOURCE_FILES).issubset(missing))
        self.assertEqual(data['runtime'], 'NOT_RUN')
        self.assertFalse(Path(self.env['HOME']).exists())
        self.assertFalse(Path(self.env['CHATGPT_CODEX_BRIDGE_STATE_DIR']).exists())
        self.assertNotIn(str(self.root), result.stderr)

    def test_truncated_xml_reports_invalid_config_and_remaining_checks(self):
        self.prepare_valid()
        truncated = b'<?xml version="1.0"?><plist version="1.0"><dict>'
        self.config.write_bytes(truncated)
        result = self.static()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout)
        data = json.loads(result.stdout)
        self.assertEqual(data['result'], 'STATIC_CHECKS_FAILED')
        self.assertEqual(data['runtime'], 'NOT_RUN')
        self.assertEqual(data['live_identity'], 'NOT_COLLECTED')
        checks = {item['field']: item['result'] for item in data['checks']}
        self.assertEqual(checks['config'], 'INVALID')
        for field in (*doctor.CONFIG_PATH_FIELDS, 'preset', 'sandbox', 'approval_policy'):
            self.assertEqual(checks[field], 'MISSING')
        for relative in doctor.SOURCE_FILES:
            self.assertEqual(checks[relative], 'PRESENT')
            self.assertEqual(checks[relative + ':digest'], 'NOT_COLLECTED')
        self.assertNotIn('Traceback', result.stderr)
        self.assertNotIn('ExpatError', result.stderr)
        self.assertNotIn(str(self.root), result.stderr)
        self.assertNotIn(str(ROOT), result.stderr)
        self.assertFalse(Path(self.env['HOME']).exists())
        self.assertFalse(Path(self.env['CHATGPT_CODEX_BRIDGE_STATE_DIR']).exists())
        self.assertEqual(self.config.read_bytes(), truncated)

    def test_static_success_ignores_runtime_paths_and_distinguishes_drift(self):
        self.prepare_valid()
        before = self.config.read_bytes()
        result = self.static()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['result'], 'STATIC_CHECKS_PASSED')
        self.assertEqual(data['live_identity'], 'NOT_COLLECTED')
        self.assertEqual(sum(x['result'] == 'NOT_COLLECTED' for x in data['checks']), len(doctor.SOURCE_FILES))
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse(Path(self.env['HOME']).exists())
        digests = self.root / 'expected.json'
        digests.write_text(json.dumps({doctor.SOURCE_FILES[0]: '0' * 64}))
        result = self.static('--expected-digests', str(digests))
        self.assertEqual(result.returncode, 1)
        checks = json.loads(result.stdout)['checks']
        self.assertEqual(sum(x['result'] == 'DRIFT' for x in checks), 1)
        self.assertEqual(sum(x['result'] == 'NOT_COLLECTED' for x in checks), len(doctor.SOURCE_FILES) - 1)

    def test_static_never_runs_subprocess_or_opens_config_references(self):
        self.prepare_valid()
        original = open
        opened = []
        def checked(path, *args, **kwargs):
            opened.append(str(path))
            self.assertNotIn(str(path), [str(self.root / f) for f in doctor.CONFIG_PATH_FIELDS])
            return original(path, *args, **kwargs)
        with patch('builtins.open', side_effect=checked), \
                patch('subprocess.run', side_effect=AssertionError('must not execute')), \
                patch('subprocess.Popen', side_effect=AssertionError('must not execute')):
            result = doctor.static_checks(self.config, self.source)
        self.assertEqual(result['result'], 'STATIC_CHECKS_PASSED')
        self.assertEqual(opened, [str(self.config)])

    def test_default_and_missing_static_args_do_not_run_runtime(self):
        for args in ((), ('--static',), ('--static', '--config', str(self.config))):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertNotIn(str(self.root), result.stderr)
            self.assertFalse(Path(self.env['HOME']).exists())

    def test_source_symlink_rejected_without_opening_target(self):
        self.prepare_valid()
        path = self.source / doctor.SOURCE_FILES[0]
        path.unlink()
        path.symlink_to(self.root / 'managed_registry')
        result = self.static()
        self.assertEqual(result.returncode, 1)
        self.assertIn(dict(field=doctor.SOURCE_FILES[0], result='INVALID'), json.loads(result.stdout)['checks'])


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('BRIDGE_TEST_OWNED_PROCESS') == '1',
                     'owned macOS reader smoke explicitly selected separately')
class OwnedMacReaderTest(unittest.TestCase):
    def test_native_reads_only_task_owned_child(self):
        with tempfile.TemporaryDirectory(prefix='bridge-owned-reader-') as tmp:
            script = Path(tmp) / 'synthetic.py'
            script.write_text('import time\ntime.sleep(30)\n')
            process = subprocess.Popen([sys.executable, '-I', str(script), '--watch'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                reader = observer.MacProcessReader()
                before, first = reader.info(process.pid)
                executable, executable_detail = reader.executable(process.pid)
                args, argv_detail = reader.argv(process.pid)
                after, last = reader.info(process.pid)
                self.assertEqual(observer.instance(before), observer.instance(after))
                self.assertEqual(before['pid'], process.pid)
                self.assertEqual(before['ppid'], os.getpid())
                self.assertEqual(before['uid'], os.getuid())
                self.assertEqual(first['actual_length'], ctypes.sizeof(observer.BsdInfo))
                self.assertEqual(last['actual_length'], first['actual_length'])
                self.assertTrue(executable)
                self.assertEqual(args['argv'], [sys.executable, '-I', str(script), '--watch'])
                self.assertEqual(argv_detail['returncode'], 0)
                self.assertGreater(executable_detail['actual_length'], 0)
            finally:
                # Only the Popen child created here; never names/historical PIDs.
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
