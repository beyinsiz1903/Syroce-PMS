"""Real dump/restore of sealed money/audit records on a disposable local DB."""
import asyncio
import subprocess
from copy import deepcopy

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from core import audit_chain
from core.audit_chain import compute_record_hash
from shared_kernel.gl_posting import compute_journal_entry_hash, verify_journal_entry_hash
from tests.test_tenant_restore_drill_smoke import drill, seed_mod
from tests.test_tenant_restore_drill_smoke import local_mongo as local_mongo  # noqa: F401


@pytest.mark.asyncio
async def test_financial_dump_restore_preserves_seals_indexes_and_tenant_boundary(local_mongo, tmp_path, monkeypatch):
    client = AsyncIOMotorClient(local_mongo)
    source, target = 'financial_source', 'financial_restored'
    financial = ('folio_charges', 'gl_journal_entries', 'audit_logs', 'audit_chain_state', 'demo_comp_reconstructions')
    try:
        await seed_mod.seed(local_mongo, source)
        database = client[source]
        for tenant in ('T1', 'T2'):
            charge = {'id': f'charge-{tenant}', 'tenant_id': tenant, 'total': 120, 'amount': 100, 'vat_amount': 20, 'currency': 'TRY'}
            await database.folio_charges.insert_one(deepcopy(charge))
            journal = {'id': f'journal-{tenant}', 'tenant_id': tenant, 'entry_no': 'FIXTURE-1', 'date': '2026-11-28', 'status': 'posted',
                       'lines': [{'account_code': '120', 'debit': 120, 'credit': 0}, {'account_code': '600', 'debit': 0, 'credit': 100}, {'account_code': '391', 'debit': 0, 'credit': 20}]}
            journal['entry_hash'] = compute_journal_entry_hash(journal)
            await database.gl_journal_entries.insert_one(journal)
            audit = {'id': f'audit-{tenant}', 'tenant_id': tenant, 'action': 'fixture_charge_posted', 'entity_id': charge['id'],
                     'timestamp': '2026-11-28T00:00:00+00:00', 'seq': 1, 'prev_hash': '', 'after_snapshot': {'total': 120}}
            audit['record_hash'] = compute_record_hash(audit, 1, '')
            await database.audit_logs.insert_one(deepcopy(audit))
            # This is the ACTUAL audit-chain-state schema: tenant identity is _id.
            await database.audit_chain_state.insert_one({'_id': tenant, 'seq': 1, 'last_hash': audit['record_hash']})
            await database.demo_comp_reconstructions.insert_one({'id': f'receipt-{tenant}', 'tenant_id': tenant, 'before': [charge], 'audit_id': audit['id'], 'audit_hash': audit['record_hash']})
        await database.gl_journal_entries.create_index([('tenant_id', 1), ('entry_no', 1)], unique=True)
        await database.audit_logs.create_index([('tenant_id', 1), ('seq', 1)], unique=True)
        await database.demo_comp_reconstructions.create_index([('tenant_id', 1), ('id', 1)], unique=True)
        original = {name: await database[name].find({'_id': 'T1'} if name == 'audit_chain_state' else {'tenant_id': 'T1'}).to_list(None) for name in (*seed_mod.COLLECTIONS, *financial)}
        archive = tmp_path / 'dump'
        dumped = await asyncio.to_thread(subprocess.run, ['mongodump', f'--uri={local_mongo}', f'--db={source}', f'--out={archive}', '--gzip'], capture_output=True)
        assert dumped.returncode == 0
        names = [*seed_mod.COLLECTIONS, *financial]
        classification = {'TENANT_SCOPED': [{'name': name, 'ref_count': 1, 'ref_files': ['fixture']} for name in names],
                          'GLOBAL_EXCLUDE': [], 'UNKNOWN_REVIEW_REQUIRED': [], 'SYSTEM_INTERNAL': [], '_summary': {'TENANT_SCOPED': len(names), 'GLOBAL_EXCLUDE': 0, 'UNKNOWN_REVIEW_REQUIRED': 0, 'SYSTEM_INTERNAL': 0}}
        monkeypatch.setattr(drill.classify_tenant_scope, 'build_report', lambda _: classification)
        # main owns an asyncio.run loop; invoke the synchronous command outside ours.
        rc = await asyncio.to_thread(drill.main, ['--backup-archive', str(archive), '--tenant-id', 'T1', '--target-db', target,
            '--source-db-name', source, '--mongo-url', local_mongo, '--prod-db-name', 'hotel_pms', '--report-dir', str(tmp_path / 'report'), '--execute'])
        assert rc == 0, 'Financial restore must include tenant-keyed audit chain state without cross-tenant state'
        restored = client[target]
        for name in names:
            query = {'_id': 'T1'} if name == 'audit_chain_state' else {'tenant_id': 'T1'}
            assert await restored[name].find(query).to_list(None) == original[name]
            assert await restored[name].count_documents({'_id': {'$ne': 'T1'}} if name == 'audit_chain_state' else {'tenant_id': {'$ne': 'T1'}}) == 0
        journal = await restored.gl_journal_entries.find_one({'tenant_id': 'T1'})
        assert verify_journal_entry_hash(journal)
        audit = await restored.audit_logs.find_one({'tenant_id': 'T1'})
        assert compute_record_hash(audit, audit['seq'], audit['prev_hash']) == audit['record_hash']
        state = await restored.audit_chain_state.find_one({'_id': 'T1'})
        assert state['last_hash'] == audit['record_hash']
        for name in ('gl_journal_entries', 'audit_logs', 'demo_comp_reconstructions'):
            indexes = await restored[name].index_information()
            assert any(index.get('unique') for key, index in indexes.items() if key != '_id_')
        # Recovery must support the next real append, not merely retain old bytes.
        monkeypatch.setattr(audit_chain, '_system_db', lambda: restored)
        next_entry = await audit_chain.append_audit_log(restored,
            {'id': 'post-restore', 'tenant_id': 'T1', 'action': 'recovery_verified',
             'timestamp': '2026-11-28T00:01:00+00:00'}, require_chain=True)
        assert next_entry['seq'] == 2
        assert next_entry['prev_hash'] == audit['record_hash']
        next_state = await restored.audit_chain_state.find_one({'_id': 'T1'})
        assert next_state['seq'] == 2 and next_state['last_hash'] == next_entry['record_hash']
        assert await restored.audit_chain_state.find_one({'_id': 'T2'}) is None
    finally:
        await client.drop_database(source)
        await client.drop_database(target)
        client.close()


def test_classifier_discovers_actual_audit_state_key():
    from pathlib import Path

    from tests.test_tenant_restore_drill import classify_mod

    report = classify_mod.build_report(Path(__file__).resolve().parents[1])
    state = next(row for row in report['TENANT_SCOPED'] if row['name'] == 'audit_chain_state')
    assert state['tenant_key'] == '_id'
    assert classify_mod.classify('unreviewed_dynamic_collection', []) == 'UNKNOWN_REVIEW_REQUIRED'
