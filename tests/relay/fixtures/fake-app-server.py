#!/usr/bin/python3
"""Synthetic protocol peer. Only launched with an isolated fixture HOME."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

home = Path(os.environ['HOME'])
assert (home / 'COMPONENT02_FIXTURE').is_file()
assert sys.argv[1:] == ['app-server', '--listen', 'stdio://']
state_file = home / 'fake-threads.json'
threads = json.loads(state_file.read_text()) if state_file.exists() else {}
thread = None
cwd = None

def send(value):
    print(json.dumps(value), flush=True)

def event(method, params):
    send(dict(method=method, params=params))

for line in sys.stdin:
    msg = json.loads(line)
    method, args = msg['method'], msg['params']
    if method == 'initialized':
        continue
    response = {}
    if method == 'initialize':
        assert args['capabilities'] == {'experimentalApi': False}
        response = {'userAgent': 'component02-fake'}
    elif method in ('thread/start', 'thread/resume'):
        assert args['approvalPolicy'] == 'never' and args['sandbox'] == 'workspace-write'
        assert args['persistExtendedHistory'] is False
        cwd = args['cwd']
        assert Path(cwd).resolve().is_relative_to(home.parent / 'workspace' / 'managed')
        if method == 'thread/start':
            assert set(args) == {'cwd','approvalPolicy','sandbox','persistExtendedHistory','experimentalRawEvents'}
            assert args['experimentalRawEvents'] is False
            thread = str(uuid.uuid4())
            threads[thread] = cwd
            state_file.write_text(json.dumps(threads))
        else:
            assert set(args) == {'cwd','approvalPolicy','sandbox','persistExtendedHistory','threadId'}
            thread = args['threadId']
            assert threads[thread] == cwd
        response = {'thread': {'id': thread, 'cwd': cwd}, 'cwd':cwd, 'approvalPolicy':'never',
                    'sandbox':{'type':'workspaceWrite','writableRoots':[cwd],
                               'readOnlyAccess':{'type':'fullAccess'},'networkAccess':False,
                               'excludeTmpdirEnvVar':True,'excludeSlashTmp':True},
                    'model':'fixture','modelProvider':'fixture','reasoningEffort':None}
        mode = (home/'mode').read_text() if (home/'mode').exists() else ''
        if mode == 'wrong-cwd':response['thread']['cwd'] = str(home)
        if mode == 'wrong-policy':response['sandbox']['type'] = 'dangerFullAccess'
        if mode == 'wrong-resume' and method == 'thread/resume':response['thread']['id'] = 'wrong'
    elif method == 'turn/start':
        assert args['threadId'] == thread and args['cwd'] == cwd
        assert args['approvalPolicy'] == 'never'
        assert args['sandboxPolicy'] == {'type':'workspaceWrite','writableRoots':[cwd],
            'readOnlyAccess':{'type':'fullAccess'},'networkAccess':False,
            'excludeTmpdirEnvVar':True,'excludeSlashTmp':True}
        prompt = args['input'][0]['text']
        assert args['input'][0]['text_elements'] == []
        if prompt == 'wrong-response':
            send({'id': 99999, 'result': {}})
            continue
        if prompt == 'exit-zero':
            sys.exit(0)
        turn = str(uuid.uuid4())
        if prompt != 'early-events':
            send({'id': msg['id'], 'result': {'turn': {'id': turn, 'status':'inProgress','items':[],'error':None}}})
        event('turn/completed', {'threadId':'foreign', 'turn': {'id':turn,'status':'completed'}})
        if prompt == 'timeout':
            continue
        if prompt == 'foreign-only':
            sys.exit(0)
        if prompt == 'agent-only':
            event('item/completed', {'threadId':thread,'turnId':turn,
                  'item':{'type':'agentMessage','text':'Completed successfully','phase':'final_answer'}})
            sys.exit(0)
        with (Path(cwd) / 'README.md').open('a') as target:
            target.write('synthetic round\n')
        (Path(cwd) / 'review-note.txt').write_text('small reviewable artifact\n')
        code = "from pathlib import Path; assert 'synthetic round' in Path('README.md').read_text()"
        if prompt in ('failed-check', 'unsupported-path-check', 'excess-files-check'):
            code = 'import sys; sys.exit(7)'
        if prompt == 'unsupported-path-check':
            (Path(cwd)/'说明.md').write_text('small unsupported artifact\n')
        if prompt == 'excess-files-check':
            for index in range(65):
                (Path(cwd)/('extra-%d.txt' % index)).write_text('small artifact\n')
        credentials = 'AWS_ACCESS_KEY_ID=AKIAEXAMPLE0000000000\nAWS_SECRET_ACCESS_KEY=fixture_only_not_real_key\n'
        if prompt in ('aws-env', 'aws-source'):
            with (Path(cwd)/('.env' if prompt == 'aws-env' else 'README.md')).open('a') as target:
                target.write(credentials)
        if prompt == 'aws-command':
            code = 'fixture = ' + repr(credentials)
        if prompt == 'private-id-artifact':(Path(cwd)/'review-note.txt').write_text(thread)
        result = subprocess.run(['python3', '-c', code], cwd=cwd, check=False)
        event('item/completed', {'threadId':thread,'turnId':turn,
              'item':{'type':'commandExecution','id':'private-command', 'command':'python3 -c '+repr(code),
                      'cwd':cwd,'exitCode':result.returncode,'status':'completed',
                      'aggregatedOutput':None,'processId':None,'commandActions':[], 'durationMs':None}})
        event('item/completed', {'threadId':thread,'turnId':turn,
              'item':{'type':'agentMessage','text':'Synthetic file check completed.','phase':'final_answer'}})
        event('turn/completed', {'threadId':thread,'turn':{'id':turn,'status':'completed','items':[],'error':None}})
        print('synthetic private stderr token=do-not-export', file=sys.stderr, flush=True)
        if prompt == 'early-events':
            send({'id': msg['id'], 'result': {'turn': {'id':turn,'status':'inProgress'}}})
        continue
    elif method == 'thread/read':
        assert args == {'threadId':thread,'includeTurns':False}
        response = {'thread':{'id':thread,'cwd':cwd}}
    else:
        raise AssertionError('unapproved protocol method')
    send({'id':msg['id'],'result':response})
