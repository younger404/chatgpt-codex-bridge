#!/usr/bin/python3
"""Actual Relay -> Guard admission/worker -> fake stdio; no installed inputs."""
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/bridge'))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

relay = load('c2relay', ROOT / 'scripts/relay/github-issue-relay.py')
guard = load('c2guard', ROOT / 'scripts/bridge/codex-mcp-guard.py')
old = load('relaytests', ROOT / 'tests/relay/test-github-issue-relay.py')
old.relay_module = relay
managed = load('managedtests', ROOT / 'tests/bridge/test-managed-repo.py')
from supervision import collect_evidence, digest, PROTOCOL
import managed_repo


class Component02Test(unittest.TestCase):
    def setUp(self):
        self.fixture = managed.ManagedRepoTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.home = self.root / 'home'
        self.home.mkdir()
        (self.home / 'COMPONENT02_FIXTURE').touch()
        self.env = mock.patch.dict(os.environ, {'HOME':str(self.home), 'PATH':'/usr/bin:/bin',
                                               'TMPDIR':str(self.root)}, clear=True)
        self.env.start(); self.addCleanup(self.env.stop)
        self.entry = dict(self.fixture.entry, alias='sample-alpha')
        beta_repo = self.root / 'beta'
        managed.run('git', 'clone', str(self.fixture.remote), str(beta_repo))
        managed.run('git', 'checkout', 'main', cwd=beta_repo)
        self.beta = dict(self.entry, alias='sample-beta', repoPath=str(beta_repo), repositoryFullName='example/sample-beta')
        self.registry_path = self.root / 'registry.json'
        self.document = {'registryVersion':managed_repo.REGISTRY_VERSION, 'repos':[self.entry,self.beta]}
        self.registry_path.write_text(json.dumps(self.document));self.registry_path.chmod(0o600)
        # Only substitute GitHub remote identity for our two local bare-origin fixtures.
        def verify(entry):
            assert entry['repoPath'] in (str(self.fixture.repo), str(beta_repo))
            assert managed.run('git','remote','get-url','origin',cwd=entry['repoPath']) == str(self.fixture.remote)
            return True
        self.verification = mock.patch.object(managed_repo, 'verify_entry', side_effect=verify)
        self.verification.start();self.addCleanup(self.verification.stop)
        self.app = self.root / 'fake-app-server'
        self.app.write_bytes((ROOT / 'tests/relay/fixtures/fake-app-server.py').read_bytes());self.app.chmod(0o700)
        self.g = guard.CodexMcpGuard(str(self.fixture.workspace),str(self.app),sandbox='workspace-write',
            approval_policy='never',preset='managed-repo',job_state_dir=str(self.root/'jobs'),
            managed_registry_path=str(self.registry_path),disk_usage_provider=lambda _:SimpleNamespace(total=1000*managed_repo.GIB,used=100*managed_repo.GIB,free=900*managed_repo.GIB))
        self.pending = []
        def defer(command):
            self.pending.append(command)
            return SimpleNamespace(pid=os.getpid())
        self.g.job_store._start_worker = defer
        self.cfg = dict(preset='managed-repo',sandbox='workspace-write',approval_policy='never',
            managed_registry=str(self.registry_path),job_state_dir=str(self.root/'jobs'),
            relay_control_repository='example/control-private',relay_allowed_authors=['fixture-owner'],
            relay_enabled_aliases=['sample-alpha','sample-beta'])
        self.cfg_path = self.root/'operator.plist';self.save_config()
        self.config = relay.OperatorConfig.load(self.cfg_path)
        self.db_path = self.root/'relay.sqlite'
        self.db = relay.RelayDatabase(self.db_path,self.config)
        self.addCleanup(lambda:self.db.close())
        self.github = old.FakeGitHub()
        self.calls = []
        owner = self
        class LocalGuard:
            def start(self):
                responses=[]; owner.g.emit=responses.append
                owner.g.handle_client_message({'jsonrpc':'2.0','id':0,'method':'initialize',
                                                'params':{'protocolVersion':'2025-06-18'}})
                assert 'result' in responses[-1]
                owner.g.handle_client_message({'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}})
                assert relay.REQUIRED_TOOLS.issubset({t['name'] for t in responses[-1]['result']['tools']})
                assert owner.g.child is None
                return relay.REQUIRED_TOOLS
            def close(self): pass
            def call_tool(self,name,args):
                owner.calls.append(name)
                responses=[]
                owner.g.emit=responses.append
                owner.g.handle_client_message({'jsonrpc':'2.0','id':2,'method':'tools/call',
                                              'params':{'name':name,'arguments':args}})
                response=responses[-1]
                if 'error' in response: raise relay.GuardMcpError(response['error']['code'])
                return response['result']['structuredContent']
        self.relay=relay.GitHubIssueRelay(self.db,self.github,LocalGuard)
        self.number=0

    def save_config(self):
        self.cfg_path.write_bytes(plistlib.dumps(self.cfg));self.cfg_path.chmod(0o600)

    def issue(self, operation='start', reference=None, **fields):
        self.number+=1
        payload=dict(schema='codex_bridge_job_v1',requestId=str(uuid.uuid4()),operation=operation)
        if operation=='start':payload.update(repoAlias='sample-alpha',taskName='synthetic check',prompt='check')
        else:payload['relayJobRef']=reference
        if operation=='reply':payload['prompt']='check'
        payload.update(fields)
        return dict(number=self.number,state='open',repository_url='https://api.github.com/repos/'+self.config.repository,
                    user={'login':'fixture-owner'},labels=['bridge-job'],body=json.dumps(payload))

    def execute_pending(self):
        while self.pending:
            command=self.pending.pop(0)
            args=guard.parse_worker_configuration(command[command.index('--run-job'):])
            # Same source worker, only its executable and HOME point to owned fixtures.
            result=guard.run_job(*args)
            self.assertEqual(result,0)

    def finish(self, issue):
        self.relay.process_issue(issue); self.execute_pending()
        self.relay.supervise_active_jobs(); self.relay.deliver_pending_results()
        return json.loads(self.db.get_by_issue(issue['number'])['resultPayload'])

    def test_two_projects_config_only_supervision_review_reply_and_retry(self):
        for alias in ('sample-alpha','sample-beta'):
            start=self.issue(repoAlias=alias)
            self.relay.process_issue(start)
            row=self.db.get_by_issue(start['number']);reference=row['relayJobRef']
            running=json.loads(row['resultPayload'])
            self.assertEqual(running['supervision']['executionState'],'queued')
            self.relay.deliver_pending_results()
            count=len(self.pending)
            query=self.issue('query',reference)
            result=self.finish(query)
            self.assertEqual(count,1)
            self.assertEqual(self.calls.count('codex-repo-start'),1 if alias=='sample-alpha' else 2)
            self.assertEqual(result['supervision']['executionState'],'queued')
            self.relay.supervise_active_jobs();self.relay.deliver_pending_results()
            row=self.db.get_by_issue(start['number']);terminal=json.loads(row['resultPayload'])
            ev=terminal['supervision']['evidence']
            self.assertEqual(ev['checks'][0]['exitCode'],0)
            self.assertEqual(ev['checksState'],'RECORDED')
            self.assertEqual(ev['artifactState'],'AVAILABLE')
            self.assertIn('synthetic round',ev['diff']);self.assertIn('review-note.txt',ev['diff'])
            self.assertEqual(ev['base'],ev['head']) # uncommitted edits still have a distinct digest
            review=self.issue('review',reference,evidenceRequestId=row['requestId'],
                              evidenceDigest=terminal['supervision']['evidenceDigest'],conclusion='accepted')
            before=list(self.calls)
            reviewed=self.finish(review)
            self.assertEqual(self.calls,before)
            self.assertEqual(reviewed['supervision']['reviewState'],'recorded')
            original_thread=row['localGuardThreadCapability']; original_branch=row['workBranch']
            self.github.fail_comment_after_accept=1
            reply=self.issue('reply',reference)
            result=self.finish(reply)
            replyrow=self.db.get_by_issue(reply['number'])
            self.assertEqual(replyrow['localGuardThreadCapability'],original_thread)
            self.assertEqual(replyrow['workBranch'],original_branch)
            self.assertEqual(result['supervision']['reviewState'],'unreviewed')
            self.assertNotEqual(result['supervision']['evidence']['candidateDigest'],ev['candidateDigest'])
            self.assertEqual(replyrow['deliveryState'],'pending')
            self.db.close(); self.db=relay.RelayDatabase(self.db_path,self.config);self.relay.database=self.db
            self.github.fail_terminal_label=1
            before=list(self.calls)
            self.relay.deliver_pending_results(); self.relay.deliver_pending_results()
            self.relay.process_issue(reply) # retry is not a new turn
            self.assertEqual(self.calls,before)
            self.assertEqual(self.db.get_by_issue(reply['number'])['deliveryState'],'delivered')
            comments=[body for number,body in self.github.comments if number==reply['number']]
            self.assertEqual(len(comments),1)
            serialized=json.dumps(self.github.comments)
            for secret in (str(self.root),original_thread,'private-command','do-not-export'):
                self.assertNotIn(secret,serialized)
            self.assertEqual(json.loads(self.db.get_by_issue(start['number'])['resultPayload']),terminal)
            print(json.dumps(dict(project=alias,rounds=2,sameThread=True,checkExit=0,
                                 artifact='AVAILABLE',candidateDigest=result['supervision']['evidence']['candidateDigest'])))

    def test_scope_and_missing_configuration_and_revocation(self):
        self.finish(self.issue())
        self.assertRaisesRegex(relay.RelayError,'JOURNAL_SCOPE_MISMATCH',relay.RelayDatabase,self.db_path,
            relay.OperatorConfig(self.config.repository,self.config.authors,self.config.prefixes,'b'*64))
        self.assertRaisesRegex(relay.RelayError,'JOURNAL_SCOPE_MISMATCH',relay.RelayDatabase,self.db_path,
            relay.OperatorConfig('example/other',self.config.authors,self.config.prefixes,self.config.installation))
        for key in ('relay_control_repository','relay_allowed_authors','relay_enabled_aliases','job_state_dir'):
            saved=self.cfg.pop(key);self.save_config()
            self.assertRaises(relay.RelayError,relay.OperatorConfig.load,self.cfg_path)
            self.cfg[key]=saved
        self.cfg['relay_enabled_aliases']=['unknown-project'];self.save_config()
        self.assertRaises(relay.RelayError,relay.OperatorConfig.load,self.cfg_path)
        self.cfg['relay_enabled_aliases']=['sample-alpha'];self.cfg['relay_branch_prefixes']={'sample-alpha':'wider/'};self.save_config()
        self.assertRaises(relay.RelayError,relay.OperatorConfig.load,self.cfg_path)
        self.cfg.pop('relay_branch_prefixes');self.save_config()
        alpha_only=relay.OperatorConfig.load(self.cfg_path)
        self.assertRaises(relay.AdmissionError,alpha_only.authorize,'sample-beta')
        self.document['repos'][0]['deploymentTier']='staging'
        self.registry_path.write_text(json.dumps(self.document))
        self.assertRaises(relay.AdmissionError,self.config.authorize,'sample-alpha')
        # Retained evidence query is independent of revoked execution permission.
        reference=self.db.get_by_issue(1)['relayJobRef']
        before=list(self.calls);self.finish(self.issue('query',reference))
        self.assertEqual(self.calls,before)
        self.assertRaises(relay.AdmissionError,self.relay.admit_issue,self.issue('reply',reference))

    def test_busy_review_binding_and_cross_source(self):
        malformed=self.issue();payload=json.loads(malformed['body']);payload['operation']=[];malformed['body']=json.dumps(payload)
        self.assertRaises(relay.AdmissionError,self.relay.admit_issue,malformed)
        start=self.issue();result=self.finish(start);reference=result['relayJobRef']
        wrong=self.issue('review',reference,evidenceRequestId=result['requestId'],evidenceDigest='0'*64,conclusion='accepted')
        self.assertRaises(relay.AdmissionError,self.relay.admit_issue,wrong)
        for field,value in [('repository_url','https://api.github.com/repos/example/other'),('user',{'login':'outsider'})]:
            issue=self.issue('query',reference);issue[field]=value
            self.assertRaises(relay.AdmissionError,self.relay.admit_issue,issue)
        first=self.issue('reply',reference);self.relay.process_issue(first)
        self.assertRaises(relay.AdmissionError,self.relay.admit_issue,self.issue('reply',reference))
        thread=self.db.get_by_issue(start['number'])['localGuardThreadCapability']
        self.assertRaises(guard.GuardAdmissionError,self.g.job_store.enqueue,'check',thread_id=thread)
        self.execute_pending()

    def test_cli_refuses_missing_config_and_scope_before_github(self):
        proc=subprocess.run(['python3',str(ROOT/'scripts/relay/github-issue-relay.py'),'--once',
                             '--config',str(self.root/'missing.plist')],capture_output=True,text=True)
        self.assertEqual(proc.returncode,64)
        self.assertIn('{"error":"OPERATOR_CONFIG_REJECTED"}',proc.stderr)
        self.assertNotIn(str(self.root),proc.stderr)
        self.cfg['relay_control_repository']='example/different-control';self.save_config()
        output=io.StringIO()
        with mock.patch.object(relay,'GitHubClient',side_effect=AssertionError('must not contact GitHub')), contextlib.redirect_stderr(output):
            code=relay.main(['--once','--config',str(self.cfg_path),'--state',str(self.db_path)])
        self.assertEqual(code,1);self.assertEqual(json.loads(output.getvalue())['error'],'JOURNAL_SCOPE_MISMATCH')

    def test_v3_explicit_binding_preserves_rows_and_v1_outbox(self):
        old_path=self.root/'old.sqlite'
        conn=sqlite3.connect(old_path)
        # Use predecessor's table creator; exact columns/user_version define v3.
        creator=object.__new__(relay.RelayDatabase);creator.connection=conn;creator._create_v3_table()
        payload=relay.build_public_result(str(uuid.uuid4()),relay.make_relay_job_ref(),'completed','historical result',repo_alias='sample-alpha')
        encoded=json.dumps(payload)
        values=(payload['requestId'],900,'c'*64,'start',payload['relayJobRef'],'sample-alpha','codex/bridge/example',
                'synthetic-job','synthetic-thread','completed',encoded,'pending',None,'then','then')
        conn.execute('INSERT INTO relay_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',values)
        conn.execute('PRAGMA user_version=3');conn.commit();conn.close();old_path.chmod(0o600)
        before=old_path.read_bytes()
        self.assertRaisesRegex(relay.RelayError,'OPERATOR_MIGRATION_REQUIRED',relay.RelayDatabase,old_path,self.config)
        self.assertEqual(before,old_path.read_bytes())
        migrated=relay.RelayDatabase(old_path,self.config,self.config.scope)
        self.addCleanup(migrated.close)
        row=migrated.get_by_issue(900)
        self.assertEqual(tuple(row)[:15],values)
        migrated_relay=relay.GitHubIssueRelay(migrated,self.github,lambda:None)
        self.github.fail_comment_after_accept=1
        migrated_relay.deliver_pending_results();migrated_relay.deliver_pending_results()
        self.assertEqual(self.github.comments,[(900,relay.format_result_comment(payload))])
        self.assertEqual(migrated.get_by_issue(900)['resultPayload'],encoded)

    def test_protocol_failures_never_become_success_or_restart(self):
        for scenario in ('wrong-response','exit-zero','foreign-only','agent-only','timeout'):
            issue=self.issue(prompt=scenario)
            self.relay.process_issue(issue)
            command=self.pending.pop(0)
            args=list(guard.parse_worker_configuration(command[command.index('--run-job'):]))
            if scenario=='timeout':args[9]=0.1
            code=guard.run_job(*args)
            self.assertEqual(code,guard.EXIT_PROTOCOL)
            state=guard.read_json_object(Path(args[0])/'status.json')
            self.assertEqual(state['status'],'interrupted')
            self.assertEqual(state['failureKind'],'timeout' if scenario=='timeout' else
                             'protocol_error' if scenario=='wrong-response' else 'process_exit')
            self.relay.supervise_active_jobs();self.relay.deliver_pending_results()
            before=self.calls.count('codex-repo-start')
            self.relay.run_once();self.relay.process_issue(issue)
            self.assertEqual(self.calls.count('codex-repo-start'),before)
            self.assertFalse(self.pending)
        self.finish(self.issue(prompt='early-events'))

    def test_policy_cwd_and_resumed_identity_are_checked(self):
        terminal=self.finish(self.issue())
        for mode in ('wrong-cwd','wrong-policy','wrong-resume'):
            (self.home/'mode').write_text(mode)
            issue=self.issue('reply',terminal['relayJobRef'])
            self.relay.process_issue(issue)
            command=self.pending.pop(0)
            args=guard.parse_worker_configuration(command[command.index('--run-job'):])
            self.assertEqual(guard.run_job(*args),guard.EXIT_PROTOCOL)
            self.relay.supervise_active_jobs()
            state=guard.read_json_object(Path(args[0])/'status.json')
            self.assertEqual(state['evidence']['checksState'],'NOT_RUN')
        (self.home/'mode').unlink()

    def test_nonzero_check_and_private_downstream_id_are_not_success_evidence(self):
        result=self.finish(self.issue(prompt='failed-check'))
        self.assertEqual(result['supervision']['evidence']['checks'][0]['exitCode'],7)
        result=self.finish(self.issue(prompt='private-id-artifact'))
        self.assertEqual(result['supervision']['evidence']['artifactState'],'WITHHELD')
        self.assertEqual(result['supervision']['evidence']['diff'],'')
        self.assertEqual(result['supervision']['evidence']['checksState'],'RECORDED')
        self.assertEqual(result['supervision']['evidence']['checks'][0]['exitCode'],0)
        for path in self.g.job_store.root.iterdir():
            if path.is_dir():
                state=guard.read_json_object(path/'status.json')
                self.assertNotIn(state['internalThreadId'],json.dumps(self.github.comments))
                self.assertEqual((path/'downstream.stderr').stat().st_mode & 0o777,0o600)

    def test_legacy_managed_thread_cannot_silently_resume(self):
        result=self.finish(self.issue())
        thread=self.db.get_by_issue(1)['localGuardThreadCapability']
        record, _, _, path=self.g.job_store.managed_record_for_thread(thread)
        record.pop('protocol');guard.atomic_write_json(path/'request.json',record)
        self.assertRaisesRegex(guard.GuardAdmissionError,'protocol migration required',
                              self.g.job_store.enqueue,'check',thread_id=thread)
        self.assertFalse(self.pending)

    def test_aws_credentials_are_withheld_in_final_projection(self):
        for scenario in ('aws-env', 'aws-source', 'aws-command'):
            with self.subTest(scenario=scenario):
                issue=self.issue(prompt=scenario)
                result=self.finish(issue)
                evidence=result['supervision']['evidence']
                comments=[body for number,body in self.github.comments if number==issue['number']]
                self.assertEqual(len(comments),1)
                self.assertEqual(self.db.get_by_issue(issue['number'])['deliveryState'],'delivered')
                for secret in ('AKIAEXAMPLE0000000000','fixture_only_not_real_key'):
                    self.assertNotIn(secret,json.dumps(comments))
                    self.assertNotIn(secret,json.dumps(result))
                if scenario == 'aws-command':
                    self.assertEqual(evidence['checksState'],'WITHHELD')
                    self.assertEqual(evidence['checks'],[])
                    self.assertEqual(evidence['artifactState'],'AVAILABLE')
                    self.assertIn('small reviewable artifact',evidence['diff'])
                else:
                    self.assertEqual(evidence['artifactState'],'WITHHELD')
                    self.assertEqual(evidence['diff'],'')
                    self.assertEqual(evidence['checksState'],'RECORDED')
                    self.assertEqual(evidence['checks'][0]['exitCode'],0)

    def test_artifact_refusal_preserves_actual_failed_check_in_final_projection(self):
        for scenario in ('unsupported-path-check', 'excess-files-check'):
            with self.subTest(scenario=scenario):
                issue=self.issue(prompt=scenario)
                result=self.finish(issue)
                evidence=result['supervision']['evidence']
                self.assertEqual(evidence['artifactState'],'WITHHELD')
                self.assertEqual(evidence['diff'],'')
                self.assertEqual(evidence['checksState'],'RECORDED')
                self.assertEqual(evidence['checks'],[dict(command="python3 -c 'import sys; sys.exit(7)'",exitCode=7)])
                comments=[body for number,body in self.github.comments if number==issue['number']]
                self.assertEqual(comments,[relay.format_result_comment(result)])
                self.assertEqual(self.db.get_by_issue(issue['number'])['deliveryState'],'delivered')

    def test_unbound_crash_is_unknown_and_query_preserves_observation_time(self):
        issue=self.issue(); row,_,_=self.relay.admit_issue(issue)
        self.relay.reconcile_unbound_active_jobs()
        result=json.loads(self.db.get_by_issue(issue['number'])['resultPayload'])
        self.assertEqual(result['status'],'interrupted');self.assertEqual(self.calls,[])
        self.relay.run_once();self.assertEqual(self.calls,[])
        terminal=self.finish(self.issue())
        observed=terminal['supervision']['observedAt']
        with mock.patch.object(relay.time,'time',return_value=observed+300):
            result=self.finish(self.issue('query',terminal['relayJobRef']))
        self.assertEqual(result['supervision']['observedAt'],observed)
        self.assertEqual(result['supervision']['freshness'],'stale')


    def test_symlink_secret_and_oversize_artifacts_are_withheld(self):
        workspace=str(self.fixture.repo);base=managed.run('git','rev-parse','HEAD',cwd=workspace)
        artifact=Path(workspace)/'artifact.txt'
        for content in ('password=synthetic-secret\n','x'*20000):
            artifact.write_text(content)
            ev=collect_evidence(workspace,base,[])
            self.assertIn(ev['artifactState'],('WITHHELD','TRUNCATED'));self.assertEqual(ev['diff'],'')
        artifact.unlink();artifact.symlink_to(self.cfg_path)
        ev=collect_evidence(workspace,base,[]);self.assertEqual(ev['artifactState'],'WITHHELD')
        artifact.unlink();artifact.write_text('x\n'*150000)
        managed.run('git','add','artifact.txt',cwd=workspace)
        managed.run('git','commit','-m','oversize historical fixture',cwd=workspace)
        base=managed.run('git','rev-parse','HEAD',cwd=workspace);artifact.unlink()
        ev=collect_evidence(workspace,base,[])
        self.assertEqual(ev['artifactState'],'WITHHELD');self.assertEqual(ev['diff'],'')


if __name__=='__main__':unittest.main()
