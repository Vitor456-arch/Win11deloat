import pytest

from clearwindows.catalog import SETTINGS, recommended_apps
from clearwindows.engine import Action, Executor, Journal


class Backend:
    def __init__(self):
        self.values = {k: {'exists': False} for k in SETTINGS}
        self.packages = {}
        self.writes = []
        self.restore_fails = False
        self.fail_write = False

    def require(self):
        pass

    def registry_read(self, setting):
        return self.values[setting.id].copy()

    def registry_write(self, setting, value):
        self.writes.append((setting.id, value))
        if self.fail_write:
            raise OSError('denied')
        self.values[setting.id] = value.copy()

    def package(self, name):
        return self.packages.get(name, [])

    def remove_package(self, name, full):
        self.packages.pop(name)

    def create_restore_point(self):
        if self.restore_fails:
            raise RuntimeError('protection disabled')
        return {'SequenceNumber': 42}


@pytest.fixture
def setup(tmp_path):
    b = Backend()
    journal = Journal(tmp_path / 'journal.sqlite3')
    return b, journal, Executor(b, journal)


def pref(key='advertising', before=None):
    return Action('registry', key, before or {'exists': False})


def test_requires_final_confirmation(setup):
    b, j, executor = setup
    with pytest.raises(PermissionError):
        executor.execute([pref()])
    assert not b.writes and not j.events()


def test_write_ahead_then_verified_completion_and_exact_absence_rollback(setup):
    b, j, executor = setup
    original = b.registry_write
    def write(setting, state):
        assert j.events()[0]['event'] in ('prepared', 'rollback_started')
        original(setting, state)
    b.registry_write = write
    assert executor.execute([pref()], confirmed=True)[0]['status'] == 'verified'
    backup = next(e for e in j.events() if e['event'] == 'prepared')
    executor.rollback(backup['id'], confirmed=True)
    assert b.values['advertising'] == {'exists': False}
    assert j.events()[0]['event'] == 'rolled_back'


def test_exact_existing_value_restored(setup):
    b, j, executor = setup
    b.values['advertising'] = {'exists': True, 'type': 4, 'value': 7}
    executor.execute([pref(before=b.values['advertising'])], confirmed=True)
    backup = next(e for e in j.events() if e['event'] == 'prepared')
    executor.rollback(backup['id'], confirmed=True)
    assert b.values['advertising']['value'] == 7


def test_refuse_external_change_and_wrong_type(setup):
    b, _, executor = setup
    action = pref()
    b.values['advertising'] = {'exists': True, 'value': 1, 'type': 4}
    with pytest.raises(ValueError, match='changed since preview'):
        executor.execute([action], confirmed=True)
    b.values['advertising'] = {'exists': True, 'value': 'bad', 'type': 1}
    with pytest.raises(ValueError, match='type'):
        executor.execute([pref(before=b.values['advertising'])], confirmed=True)
    assert not b.writes


def test_failed_restore_blocks_all_mutation(setup):
    b, j, executor = setup
    b.restore_fails = True
    with pytest.raises(RuntimeError, match='no queued changes'):
        executor.execute([pref()], confirmed=True, restore_requested=True)
    assert not b.writes
    assert j.events()[0]['event'] == 'restore_failed'


def test_unknown_target_and_duplicate_blocked(setup):
    b, _, executor = setup
    for actions in ([pref('disable-defender')], [pref(), pref()], [Action('shell', 'anything', {})]):
        with pytest.raises(ValueError):
            executor.execute(actions, confirmed=True)
    assert not b.writes


def test_failure_stops_following_actions_and_never_claims_success(setup):
    b, j, executor = setup
    b.fail_write = True
    result = executor.execute([pref(), pref('suggestions')], confirmed=True)
    assert result[0]['status'] == 'failed'
    assert len(b.writes) == 1
    assert not any(e['event'] == 'completed' for e in j.events())
    assert j.events()[0]['payload']['remaining'] == 1


def test_interrupted_session_blocks_new_work_until_reconciled(setup):
    b, j, executor = setup
    backup = j.add('interrupted', 'prepared', {'action': {'kind': 'registry', 'target': 'advertising', 'expected': {'exists': False}}, 'before': {'exists': False}})
    with pytest.raises(RuntimeError, match='Interrupted'):
        executor.execute([pref('suggestions')], confirmed=True)
    assert not b.writes
    executor.reconcile(backup)
    assert not j.unresolved()
    executor.execute([pref('suggestions')], confirmed=True)


def test_interrupted_success_can_be_reconciled_and_restored(setup):
    b, j, executor = setup
    backup = j.add('interrupted', 'prepared', {'action': {'kind': 'registry', 'target': 'advertising', 'expected': {'exists': False}}, 'before': {'exists': False}})
    b.values['advertising'] = {'exists': True, 'type': 4, 'value': 0}
    executor.reconcile(backup)
    assert j.events()[0]['event'] == 'completed'
    executor.rollback(backup, confirmed=True)
    assert b.values['advertising'] == {'exists': False}


def test_rollback_refuses_to_overwrite_new_external_preference(setup):
    b, j, executor = setup
    executor.execute([pref()], confirmed=True)
    backup = next(e for e in j.events() if e['event'] == 'prepared')
    b.values['advertising'] = {'exists': True, 'value': 99, 'type': 4}
    with pytest.raises(ValueError, match='externally'):
        executor.rollback(backup['id'], confirmed=True)
    assert b.values['advertising']['value'] == 99


def package(name='Microsoft.BingNews', **overrides):
    return {'Name': name, 'PackageFullName': name + '_123', 'NonRemovable': False, 'IsFramework': False, 'IsResourcePackage': False, **overrides}


def test_only_observed_removable_catalog_packages_recommended():
    good = package()
    bad = [package('Microsoft.WindowsStore'), package(NonRemovable=True), package(IsFramework=True), package(IsResourcePackage=True), {'Name': 'Microsoft.BingNews'}]
    assert recommended_apps([good, *bad], 2) == [good]


def test_app_removal_verified_and_not_automatically_reversible(setup):
    b, j, executor = setup
    p = package()
    b.packages[p['Name']] = [p]
    executor.execute([Action('appx', p['Name'], p)], confirmed=True)
    assert b.package(p['Name']) == []
    backup = next(e for e in j.events() if e['event'] == 'prepared')
    with pytest.raises(ValueError, match='not supported'):
        executor.rollback(backup['id'], confirmed=True)


def test_protected_and_changed_package_blocked(setup):
    b, _, executor = setup
    p = package()
    for installed in [package(NonRemovable=True), package(PackageFullName='new-version'), package(IsFramework=True)]:
        b.packages[p['Name']] = [installed]
        with pytest.raises(ValueError):
            executor.execute([Action('appx', p['Name'], p)], confirmed=True)


def test_journal_survives_reopen(setup):
    _, j, executor = setup
    executor.execute([pref()], confirmed=True)
    assert Journal(j.path).events() == j.events()


def test_unknown_package_protection_flags_fail_closed(setup):
    b, _, executor = setup
    p = package(NonRemovable=None)
    b.packages[p['Name']] = [p]
    assert recommended_apps([p], 2) == []
    with pytest.raises(ValueError, match='Protected'):
        executor.execute([Action('appx', p['Name'], p)], confirmed=True)


def test_revalidation_failure_records_partial_completion(setup):
    b, j, executor = setup
    write = b.registry_write
    def changed_externally(setting, state):
        write(setting, state)
        b.values['suggestions'] = {'exists': True, 'value': 1, 'type': 4}
    b.registry_write = changed_externally
    results = executor.execute([pref(), pref('suggestions')], confirmed=True)
    assert [r['status'] for r in results] == ['verified', 'failed']
    assert any(e['event'] == 'validation_failed' for e in j.events())
    assert j.events()[0]['event'] == 'finished'


def test_interrupted_rollback_blocks_new_sessions_until_verified(setup):
    b, j, executor = setup
    executor.execute([pref()], confirmed=True)
    backup = next(e for e in j.events() if e['event'] == 'prepared')
    j.add(backup['session'], 'rollback_started', {'backup_id': backup['id']})
    assert j.unresolved()
    with pytest.raises(RuntimeError, match='Interrupted'):
        executor.execute([pref('suggestions')], confirmed=True)
    with pytest.raises(RuntimeError, match='Interrupted recovery'):
        executor.reconcile(backup['id'])
    # Simulate interruption after the actual restore but before verification.
    b.values['advertising'] = {'exists': False}
    executor.reconcile(backup['id'])
    assert not j.unresolved()
    assert any(e['event'] == 'rolled_back' for e in j.events())
