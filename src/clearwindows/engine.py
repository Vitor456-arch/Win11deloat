"""Durable write-ahead journal and explicit execution/rollback boundaries."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from .catalog import APPS, SETTINGS


def now():
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Action:
    kind: str
    target: str
    expected: dict

    @property
    def key(self):
        return self.kind + ':' + self.target


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, session TEXT NOT NULL, time TEXT NOT NULL,
                event TEXT NOT NULL, payload TEXT NOT NULL)''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def add(self, session, event, payload):
        with self.connect() as db:
            cur = db.execute('INSERT INTO events(session,time,event,payload) VALUES (?,?,?,?)',
                             (session, now(), event, json.dumps(payload)))
            return cur.lastrowid

    def events(self):
        with self.connect() as db:
            return [dict(id=r[0], session=r[1], time=r[2], event=r[3], payload=json.loads(r[4]))
                    for r in db.execute('SELECT id,session,time,event,payload FROM events ORDER BY id DESC')]

    def unresolved(self):
        """Interrupted operations are unknown, never silently retried or called successful."""
        events = self.events()
        resolved = {e['payload'].get('backup_id') for e in events if e['event'] in ('completed', 'failed')}
        rolled = {e['payload'].get('backup_id') for e in events if e['event'] == 'rolled_back'}
        pending_rollback = {e['payload'].get('backup_id') for e in events if e['event'] == 'rollback_started'} - rolled
        return [e for e in events if e['event'] == 'prepared' and (e['id'] not in resolved or e['id'] in pending_rollback)]


class Executor:
    def __init__(self, backend, journal):
        self.backend, self.journal = backend, journal

    def validate(self, actions):
        self.backend.require()
        if not actions:
            raise ValueError('Queue is empty')
        keys = set()
        for action in actions:
            if action.key in keys:
                raise ValueError('Duplicate or conflicting action: ' + action.key)
            keys.add(action.key)
            if action.kind == 'registry':
                if action.target not in SETTINGS:
                    raise ValueError('Unknown setting')
                current = self.backend.registry_read(SETTINGS[action.target])
                if current != action.expected:
                    raise ValueError('Setting changed since preview: ' + action.target)
                if current.get('exists') and current.get('type') != 4:
                    raise ValueError('Unexpected Registry value type; refusing to overwrite')
            elif action.kind == 'appx':
                if action.target not in APPS:
                    raise ValueError('Package is not in reviewed optional-app catalog')
                packages = self.backend.package(action.target)
                if len(packages) != 1:
                    raise ValueError('Package absent or ambiguous; scan again')
                p = packages[0]
                if any(p.get(k) is not False for k in ('NonRemovable', 'IsFramework', 'IsResourcePackage')):
                    raise ValueError('Protected package')
                if p.get('PackageFullName') != action.expected.get('PackageFullName'):
                    raise ValueError('Package changed since preview')
            else:
                raise ValueError('Unsupported action type')

    def execute(self, actions, *, confirmed=False, restore_requested=False, progress=None):
        if not confirmed:
            raise PermissionError('Explicit final confirmation is required')
        self.validate(actions)
        if self.journal.unresolved():
            raise RuntimeError('Interrupted operations need reconciliation in Recovery before a new session')
        session = str(uuid.uuid4())
        self.journal.add(session, 'session', {'actions': [asdict(a) for a in actions], 'restore_requested': restore_requested})
        if restore_requested:
            try:
                point = self.backend.create_restore_point()
                self.journal.add(session, 'restore_point', point)
            except Exception as exc:
                self.journal.add(session, 'restore_failed', {'error': str(exc)})
                raise RuntimeError('Requested restore point failed; no queued changes applied. ' + str(exc)) from exc
        results = []
        for index, action in enumerate(actions):
            if progress:
                progress(index, len(actions), action.key)
            # Recheck after any previous action or restore point operation.
            try:
                self.validate([action])
            except Exception as exc:
                self.journal.add(session, 'validation_failed', {'action': asdict(action), 'error': str(exc)})
                results.append({'action': action.key, 'status': 'failed', 'error': str(exc)})
                break
            backup_id = self.journal.add(session, 'prepared', {'action': asdict(action), 'before': action.expected})
            try:
                if action.kind == 'registry':
                    setting = SETTINGS[action.target]
                    after = {'exists': True, 'value': setting.value, 'type': 4}
                    self.backend.registry_write(setting, after)
                    if self.backend.registry_read(setting) != after:
                        raise RuntimeError('Registry write could not be verified')
                else:
                    self.backend.remove_package(action.target, action.expected['PackageFullName'])
                    if self.backend.package(action.target):
                        raise RuntimeError('Package removal could not be verified')
                    after = {'removed': True, 'reinstall': 'Use Microsoft Store; availability and app data recovery are not guaranteed.'}
                self.journal.add(session, 'completed', {'backup_id': backup_id, 'action': asdict(action), 'after': after})
                results.append({'action': action.key, 'status': 'verified'})
            except Exception as exc:
                self.journal.add(session, 'failed', {'backup_id': backup_id, 'action': asdict(action), 'error': str(exc), 'state': 'unknown; inspect before retry or recovery'})
                results.append({'action': action.key, 'status': 'failed', 'error': str(exc)})
                break  # Stop on failure; no hidden best-effort continuation.
        self.journal.add(session, 'finished', {'results': results, 'remaining': len(actions) - len(results)})
        return results

    def rollback(self, backup_id, *, confirmed=False):
        if not confirmed:
            raise PermissionError('Recovery requires explicit confirmation')
        events = self.journal.events()
        entry = next((e for e in events if e['id'] == backup_id and e['event'] == 'prepared'), None)
        if not entry:
            raise ValueError('Backup not found')
        action = Action(**entry['payload']['action'])
        restored = {e['payload'].get('backup_id') for e in events if e['event'] == 'rolled_back'}
        if any(e['event'] == 'prepared' and e['id'] > backup_id and e['id'] not in restored
               and e['payload']['action']['kind'] == action.kind and e['payload']['action']['target'] == action.target for e in events):
            raise ValueError('Restore newer backups for this preference first')
        if action.kind != 'registry' or action.target not in SETTINGS:
            raise ValueError('Automatic application reinstall is not supported; use Microsoft Store')
        if any(e['event'] == 'rolled_back' and e['payload'].get('backup_id') == backup_id for e in events):
            raise ValueError('This backup was already restored')
        setting = SETTINGS[action.target]
        current = self.backend.registry_read(setting)
        proposed = {'exists': True, 'value': setting.value, 'type': 4}
        before = entry['payload']['before']
        if current not in (proposed, before):
            raise ValueError('Setting was changed externally; recovery would overwrite a newer preference')
        self.journal.add(entry['session'], 'rollback_started', {'backup_id': backup_id, 'current': current})
        self.backend.registry_write(setting, before)
        if self.backend.registry_read(setting) != before:
            raise RuntimeError('Rollback verification failed')
        self.journal.add(entry['session'], 'rolled_back', {'backup_id': backup_id})
        # Resolve an interrupted prepared action after checking and restoring its state.
        if any(e['id'] == backup_id for e in self.journal.unresolved()):
            self.journal.add(entry['session'], 'failed', {'backup_id': backup_id, 'state': 'recovered', 'error': 'Interrupted operation restored'})
        return 'Original value restored and verified'

    def reconcile(self, backup_id):
        """Read-only inspection resolves interruption only when actual state is known."""
        entry = next((e for e in self.journal.unresolved() if e['id'] == backup_id), None)
        if not entry:
            raise ValueError('Not an unresolved operation')
        action = Action(**entry['payload']['action'])
        before = entry['payload']['before']
        pending_rollback = any(e['event'] == 'rollback_started' and e['payload'].get('backup_id') == backup_id for e in self.journal.events())
        if action.kind == 'registry':
            state = self.backend.registry_read(SETTINGS[action.target])
            after = {'exists': True, 'value': SETTINGS[action.target].value, 'type': 4}
            if pending_rollback:
                if state != before:
                    raise RuntimeError('Interrupted recovery: use Restore original Registry value to finish recovery')
                self.journal.add(entry['session'], 'rolled_back', {'backup_id': backup_id, 'reconciled': True})
                self.journal.add(entry['session'], 'failed', {'backup_id': backup_id, 'error': 'Interrupted operation recovered', 'state': 'original restored'})
            elif state == after:
                self.journal.add(entry['session'], 'completed', {'backup_id': backup_id, 'action': asdict(action), 'after': after, 'reconciled': True})
            elif state == before:
                self.journal.add(entry['session'], 'failed', {'backup_id': backup_id, 'error': 'Interrupted; original value still present', 'state': 'unchanged'})
            else:
                raise RuntimeError('Current state differs from both before and proposed values; manual review required')
        elif action.kind == 'appx':
            packages = self.backend.package(action.target)
            if not packages:
                self.journal.add(entry['session'], 'completed', {'backup_id': backup_id, 'action': asdict(action), 'after': {'removed': True}, 'reconciled': True})
            elif len(packages) == 1 and packages[0]['PackageFullName'] == before['PackageFullName']:
                self.journal.add(entry['session'], 'failed', {'backup_id': backup_id, 'error': 'Interrupted; original package still installed', 'state': 'unchanged'})
            else:
                raise RuntimeError('Package state changed externally; manual review required')
        return 'Interrupted operation reconciled against current system state'
