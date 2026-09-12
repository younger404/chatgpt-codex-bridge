"""Read-only macOS process observation. No service discovery, start or cleanup."""
import ctypes as C
import datetime
import errno
import hashlib
import math
import os
from pathlib import Path
import plistlib
import re
import struct
import subprocess
import sys
import time


WINDOW_SECONDS = 15
FILE_ROLES = ('plist', 'launcher', 'runner', 'interpreter', 'framework', 'application')


class ReadFailure(Exception):
    def __init__(self, detail):
        super().__init__(detail.get('operation', 'read'))
        self.detail = detail


class ObservationFailure(Exception):
    def __init__(self, category):
        super().__init__(category)
        self.category = category


def classify(detail):
    if detail.get('errno') in (errno.EACCES, errno.EPERM):
        return 'PERMISSION_DENIED'
    if detail.get('errno') == errno.ESRCH:
        return 'PROCESS_EXITED'
    return 'READ_ERROR'


class BsdInfo(C.Structure):
    # proc_bsdinfo / PROC_PIDTBSDINFO, unchanged from the retained observer.
    _fields_ = ([(n, C.c_uint32) for n in (
        'flags', 'status', 'xstatus', 'pid', 'ppid', 'uid', 'gid', 'ruid',
        'rgid', 'svuid', 'svgid', 'reserved')]
        + [('comm', C.c_char * 16), ('name', C.c_char * 32)]
        + [(n, C.c_uint32) for n in ('nfiles', 'pgid', 'pjobc', 'tdev', 'tpgid')]
        + [('nice', C.c_int32), ('start_sec', C.c_uint64), ('start_usec', C.c_uint64)])


class MacProcessReader:
    def __init__(self):
        if sys.platform != 'darwin':
            raise RuntimeError('macOS reader required')
        self.lib = C.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        self.lib.proc_pidinfo.argtypes = [C.c_int, C.c_int, C.c_uint64, C.c_void_p, C.c_int]
        self.lib.proc_pidinfo.restype = C.c_int
        self.lib.proc_pidpath.argtypes = [C.c_int, C.c_void_p, C.c_uint32]
        self.lib.proc_pidpath.restype = C.c_int
        self.libc = C.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        self.libc.sysctl.argtypes = [C.POINTER(C.c_int), C.c_uint, C.c_void_p,
                                   C.POINTER(C.c_size_t), C.c_void_p, C.c_size_t]
        self.libc.sysctl.restype = C.c_int

    def info(self, pid):
        value = BsdInfo()
        expected = C.sizeof(value)
        detail = dict(operation='proc_pidinfo', actual_length=None,
                      expected_length=expected, errno=None)
        try:
            C.set_errno(0)
            length = self.lib.proc_pidinfo(pid, 3, 0, C.byref(value), expected)
            error = C.get_errno()
        except Exception as exc:
            detail.update(errno=getattr(exc, 'errno', None), exception_type=type(exc).__name__,
                          exception=str(exc))
            raise ReadFailure(detail) from exc
        detail.update(actual_length=length, errno=error)
        if length != expected:
            raise ReadFailure(detail)
        return {n: getattr(value, n) for n in (
            'pid', 'ppid', 'uid', 'pgid', 'status', 'start_sec', 'start_usec')}, detail

    def executable(self, pid):
        buf = C.create_string_buffer(4096)
        C.set_errno(0)
        length = self.lib.proc_pidpath(pid, buf, len(buf))
        error = C.get_errno()
        detail = dict(operation='proc_pidpath', actual_length=length,
                      buffer_length=len(buf), errno=error)
        if length <= 0:
            raise ReadFailure(detail)
        return os.fsdecode(buf.value), detail

    def argv(self, pid):
        mib = (C.c_int * 3)(1, 49, pid)  # CTL_KERN / KERN_PROCARGS2
        size = C.c_size_t(1024 * 1024)
        buf = C.create_string_buffer(size.value)
        C.set_errno(0)
        rc = self.libc.sysctl(mib, 3, buf, C.byref(size), None, 0)
        error = C.get_errno()
        detail = dict(operation='sysctl_KERN_PROCARGS2', returncode=rc,
                      actual_length=size.value, errno=error)
        if rc != 0:
            raise ReadFailure(detail)
        try:
            raw = buf.raw[:size.value]
            argc = struct.unpack_from('i', raw)[0]
            if not 0 < argc < 100:
                raise ValueError('invalid argc')
            end = raw.index(b'\0', 4)
            executable = os.fsdecode(raw[4:end])
            i = end + 1
            while i < len(raw) and raw[i] == 0:
                i += 1
            args = []
            for _ in range(argc):
                end = raw.index(b'\0', i)
                args.append(os.fsdecode(raw[i:end]))
                i = end + 1
            # Environment bytes are never decoded or returned.
            return dict(kernel_exec_path=executable, argv=args), detail
        except (ValueError, struct.error) as exc:
            detail.update(exception_type=type(exc).__name__, exception=str(exc))
            raise ReadFailure(detail) from exc

    def independent(self, pid, remaining):
        command = ['/usr/sbin/lsof', '-nP', '-a', '-p', str(pid), '-d', 'txt', '-F', 'pn']
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise ReadFailure(dict(operation='lsof', timeout=True, errno=None,
                                   returncode=None, command=command,
                                   stdout=(exc.stdout or b'').decode(errors='replace')
                                   if isinstance(exc.stdout, bytes) else exc.stdout,
                                   stderr=(exc.stderr or b'').decode(errors='replace')
                                   if isinstance(exc.stderr, bytes) else exc.stderr)) from exc
        detail = dict(operation='lsof', command=command, returncode=result.returncode,
                      stdout=result.stdout, stderr=result.stderr, errno=None)
        if result.returncode != 0:
            raise ReadFailure(detail)
        paths = sorted({os.path.realpath(line[1:]) for line in result.stdout.splitlines()
                        if line.startswith('n')})
        return paths, detail


def validate_contract(contract):
    for key in ('pid', 'uid', 'ppid'):
        if (type(contract.get(key)) is not int
                or not (1 if key == 'pid' else 0) <= contract[key] <= (2**32 - 1 if key == 'uid' else 2**31 - 1)):
            raise ValueError('invalid identity integer')
    started = contract.get('started_monotonic')
    if type(started) not in (float, int) or not math.isfinite(started) or started < 0:
        raise ValueError('invalid monotonic start')
    if not isinstance(contract.get('label'), str) or not re.fullmatch(
            r'[A-Za-z0-9][A-Za-z0-9.-]{0,127}', contract['label']):
        raise ValueError('invalid label')
    for role in FILE_ROLES:
        entry = contract.get('files', {}).get(role, {})
        path = entry.get('path')
        if not isinstance(path, str) or not os.path.isabs(path):
            raise ValueError('missing absolute identity path')
        if not re.fullmatch(r'[0-9a-f]{64}', entry.get('sha256', '')):
            raise ValueError('missing expected identity digest')


def launcher_identity(contract):
    values = {}
    for role in FILE_ROLES:
        entry = contract['files'][role]
        path = Path(entry['path'])
        if os.path.realpath(path) != str(path) or not path.is_file():
            raise ObservationFailure('IDENTITY_CONFLICT')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry['sha256']:
            raise ObservationFailure('IDENTITY_CONFLICT')
        values[role] = dict(path=str(path), sha256=digest)
    with open(values['plist']['path'], 'rb') as source:
        plist = plistlib.load(source)
    if plist.get('Label') != contract['label'] or plist.get('ProgramArguments') != [
            values['launcher']['path'], values['runner']['path']]:
        raise ObservationFailure('IDENTITY_CONFLICT')
    return values, dict(operation='launcher_identity', errno=None)


def instance(value):
    return tuple(value[key] for key in ('pid', 'ppid', 'uid', 'pgid', 'start_sec', 'start_usec'))


def observe_process(contract, reader, deadline, clock=time.monotonic):
    """Always return partial private evidence; only full reads can be candidates."""
    sample = dict(state='READ_ERROR', complete=False, steps=[], failed_step=None)

    def step(name, call):
        item = dict(step=name, at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    monotonic=clock(), result='NOT_RUN')
        sample['steps'].append(item)
        sample['failed_step'] = name
        if clock() >= deadline:
            raise ObservationFailure('TIMEOUT')
        try:
            value, detail = call()
        except ReadFailure as exc:
            item.update(result='FAILED', detail=exc.detail)
            raise ObservationFailure('TIMEOUT' if exc.detail.get('timeout') else classify(exc.detail))
        except Exception as exc:
            detail = dict(errno=getattr(exc, 'errno', None), exception_type=type(exc).__name__,
                          exception=str(exc))
            item.update(result='FAILED', detail=detail)
            raise ObservationFailure(exc.category if isinstance(exc, ObservationFailure)
                                     else classify(detail)) from exc
        item.update(result='READ', value=value, detail=detail)
        if clock() >= deadline:
            raise ObservationFailure('TIMEOUT')
        return value

    def check_process(value):
        if value.get('status') == 5:  # SZOMB: actual BSD observation, not guessed exit status.
            raise ObservationFailure('PROCESS_EXITED')
        if any(value.get(k) != contract[k] for k in ('pid', 'ppid', 'uid')) or value['start_sec'] <= 0:
            raise ObservationFailure('IDENTITY_CONFLICT')

    try:
        before = step('before', lambda: reader.info(contract['pid']))
        check_process(before)
        executable = step('executable', lambda: reader.executable(contract['pid']))
        args = step('argv', lambda: reader.argv(contract['pid']))
        after = step('after', lambda: reader.info(contract['pid']))
        check_process(after)
        if instance(before) != instance(after):
            raise ObservationFailure('IDENTITY_CONFLICT')
        sample['failed_step'] = 'identity'
        paths = {role: contract['files'][role]['path'] for role in FILE_ROLES}
        sample['process'] = before
        final = (executable == paths['interpreter']
                 and args['kernel_exec_path'] == paths['interpreter']
                 and args['argv'] == [paths['interpreter'], paths['application'], '--watch'])
        starting = (executable == paths['launcher']
                    and args['kernel_exec_path'] == paths['launcher']
                    and args['argv'] == [paths['launcher'], paths['runner']])
        if not final and not starting:
            raise ObservationFailure('IDENTITY_CONFLICT')
        sample.update(state='COMPLETE_CANDIDATE' if final else 'STARTING', failed_step=None)
    except ObservationFailure as exc:
        sample['state'] = exc.category
    except Exception as exc:
        sample['error'] = dict(exception_type=type(exc).__name__, exception=str(exc),
                               errno=getattr(exc, 'errno', None))
        sample['state'] = classify(sample['error'])
    sample['not_run_steps'] = [name for name in ('before', 'executable', 'argv', 'after')
                               if not any(s['step'] == name and s['result'] != 'NOT_RUN'
                                          for s in sample['steps'])]
    return sample


def observe_window(contract, reader, clock=time.monotonic, sleep=time.sleep):
    """One caller-supplied start and deadline; never start, restart or signal."""
    report = dict(result='READ_ERROR', complete=False, samples=[], checks=[],
                  target_exit_status=None, cleanup_exit_status=None,
                  started_monotonic=contract['started_monotonic'],
                  deadline=contract['started_monotonic'] + WINDOW_SECONDS)
    deadline = report['deadline']
    initial = None

    def check(name, call):
        item = dict(step=name, at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    monotonic=clock(), result='NOT_RUN')
        report['checks'].append(item)
        if clock() >= deadline:
            raise ObservationFailure('TIMEOUT')
        try:
            value, detail = call()
            item.update(result='READ', value=value, detail=detail)
        except ReadFailure as exc:
            item.update(result='FAILED', detail=exc.detail)
            raise ObservationFailure('TIMEOUT' if exc.detail.get('timeout') else classify(exc.detail))
        except Exception as exc:
            item.update(result='FAILED', detail=dict(errno=getattr(exc, 'errno', None),
                        exception_type=type(exc).__name__, exception=str(exc)))
            raise ObservationFailure(exc.category if isinstance(exc, ObservationFailure)
                                     else classify(item['detail'])) from exc
        if clock() >= deadline:
            raise ObservationFailure('TIMEOUT')
        return value

    def independent():
        remaining = deadline - clock()
        if remaining <= 0:
            raise ObservationFailure('TIMEOUT')
        return reader.independent(contract['pid'], remaining)

    try:
        if contract['started_monotonic'] > clock():
            raise ObservationFailure('INVALID_START_TIME')
        check('launcher', lambda: launcher_identity(contract))
        while clock() < deadline:
            sample = observe_process(contract, reader, deadline, clock)
            report['samples'].append(sample)
            if sample['state'] not in ('STARTING', 'COMPLETE_CANDIDATE'):
                raise ObservationFailure(sample['state'])
            current = instance(sample['process'])
            if initial is None:
                initial = current
            if initial != current:
                raise ObservationFailure('IDENTITY_CONFLICT')
            if sample['state'] == 'COMPLETE_CANDIDATE':
                files = check('independent', independent)
                if any(contract['files'][role]['path'] not in files for role in ('interpreter', 'framework')):
                    raise ObservationFailure('IDENTITY_CONFLICT')
                final = observe_process(contract, reader, deadline, clock)
                report['samples'].append(final)
                if final['state'] != 'COMPLETE_CANDIDATE':
                    raise ObservationFailure(final['state'] if final['state'] != 'STARTING' else 'IDENTITY_CONFLICT')
                if instance(final['process']) != initial:
                    raise ObservationFailure('IDENTITY_CONFLICT')
                # Recheck bytes/plist within the same window, after process reads.
                check('launcher_final', lambda: launcher_identity(contract))
                final['complete'] = True
                report.update(result='COMPLETE', complete=True)
                return report
            sleep(min(0.2, max(0, deadline - clock())))
        raise ObservationFailure('TIMEOUT')
    except ObservationFailure as exc:
        report['result'] = exc.category
    except Exception as exc:
        report['error'] = dict(exception_type=type(exc).__name__, exception=str(exc),
                               errno=getattr(exc, 'errno', None))
        report['result'] = classify(report['error'])
    return report
