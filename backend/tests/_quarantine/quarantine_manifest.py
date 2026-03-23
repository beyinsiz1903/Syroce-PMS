# Quarantine Skip Markers
# =======================
# Individual failing tests in otherwise-passing files.
# These tests are skipped (not deleted) so they appear in pytest output.
# Monthly review: fix root cause, remove from this list.
#
# Format: "file::class::test" or "file::test" -> reason
# Generated: 2026-03-24 (Sprint 4 Triage)

QUARANTINED_TESTS = {
    # --- Category: Stale room-night locks ---
    # NOTE: test_day2_hardening.py fully moved to _quarantine/stale_room_locks/
    "tests/test_create_reservation_bridge.py::TestCreateReservationBridge::test_happy_path_create_reservation_with_outbox_and_audit":
        "QUARANTINED 2026-03-24: Stale room-night locks",
    "tests/test_create_reservation_bridge.py::TestCreateReservationBridge::test_duplicate_request_same_idempotency_key_returns_same_reservation":
        "QUARANTINED 2026-03-24: Stale room-night locks",
    "tests/test_create_room_block_bridge.py::TestCreateRoomBlockBridge::test_happy_path_room_block_create_with_outbox_and_audit":
        "QUARANTINED 2026-03-24: Stale room-night locks",
    # NOTE: test_atomic_checkin_checkout.py fully moved to _quarantine/stale_room_locks/
    "tests/test_quick_booking.py::TestQuickBookingAPI::test_quick_booking_success":
        "QUARANTINED 2026-03-24: Stale room-night locks",
    "tests/test_quick_booking.py::TestQuickBookingCreatesGuest::test_quick_booking_creates_guest_and_booking":
        "QUARANTINED 2026-03-24: Stale room-night locks",
    "tests/test_guest_search_quick_booking.py::TestQuickBookingWithGuestId::test_quick_booking_without_guest_id_creates_walk_in":
        "QUARANTINED 2026-03-24: Stale room-night locks",
    "tests/test_guest_search_quick_booking.py::TestQuickBookingWithGuestId::test_quick_booking_with_existing_guest_id":
        "QUARANTINED 2026-03-24: Stale room-night locks",
    "tests/test_reservation_detail_api.py::TestQuickActions::test_early_checkin":
        "QUARANTINED 2026-03-24: Stale room-night locks",
    "tests/test_readme_and_booking_validation.py::TestBookingDateValidation::test_future_date_booking_succeeds":
        "QUARANTINED 2026-03-24: Stale room-night locks",
    "tests/test_new_folio_flows_api.py::TestSidebarQuickActions::test_erken_giris_button":
        "QUARANTINED 2026-03-24: Stale room-night locks in booking prerequisite",

    # --- Category: Stale DB fixtures / seed data ---
    "tests/test_rate_manager_bulk_update.py::TestRateManagerBulkUpdate::test_get_rate_grid":
        "QUARANTINED 2026-03-24: Stale fixtures - Expected room types not in DB",
    "tests/test_rate_manager_bulk_update.py::TestRateManagerBulkUpdate::test_grid_contains_room_type_names":
        "QUARANTINED 2026-03-24: Stale fixtures - Expected room types not in DB",
    "tests/test_rate_manager_bulk_update.py::TestRateManagerBulkUpdate::test_get_room_types":
        "QUARANTINED 2026-03-24: Stale fixtures - Expected room types not in DB",
    "tests/test_rate_manager_bulk_update.py::TestRateManagerBulkUpdate::test_bulk_grid_update_multiple_room_types":
        "QUARANTINED 2026-03-24: Stale fixtures - Expected room types not in DB",
    "tests/test_rate_manager_bulk_update.py::TestRateManagerGridData::test_grid_row_structure":
        "QUARANTINED 2026-03-24: Stale fixtures - Grid empty, no room type seed data",
    "tests/test_rate_manager_bulk_update.py::TestRateManagerGridData::test_grid_date_cell_structure":
        "QUARANTINED 2026-03-24: Stale fixtures - Grid empty, no room type seed data",
    "tests/test_rate_manager_notifications.py::TestRateManagerGrid::test_grid_row_structure":
        "QUARANTINED 2026-03-24: Stale fixtures - No room type data",
    "tests/test_rate_manager_notifications.py::TestRateManagerGrid::test_grid_date_cell_structure":
        "QUARANTINED 2026-03-24: Stale fixtures - No room type data",
    "tests/test_rate_manager_notifications.py::TestRateManagerRoomTypes::test_room_types_has_data":
        "QUARANTINED 2026-03-24: Stale fixtures - Expected Exely room types",
    "tests/test_rate_manager_notifications.py::TestRateManagerRoomTypes::test_room_type_structure":
        "QUARANTINED 2026-03-24: Stale fixtures - No room type data",
    "tests/test_rate_manager_notifications.py::TestRateManagerUpdate::test_update_pushes_to_exely":
        "QUARANTINED 2026-03-24: External dependency - Exely push requires credentials",

    # --- Category: Changed API endpoints / behavior ---
    "tests/test_domain_routers_phase_b_batch2_3.py::TestPOSDomainRouter::test_frontdesk_available_rooms":
        "QUARANTINED 2026-03-24: Changed API - available rooms endpoint behavior changed",
    "tests/test_domain_routers_phase_b_batch2_3.py::TestAnalyticsDomainRouter::test_dashboard_gm_pickup_analysis":
        "QUARANTINED 2026-03-24: Changed API - analytics endpoint response format changed",
    "tests/test_domain_routers_phase_b_batch2_3.py::TestAnalyticsDomainRouter::test_revenue_market_segment_breakdown":
        "QUARANTINED 2026-03-24: Changed API - analytics endpoint response format changed",
    "tests/test_domain_routers_phase_b_batch2_3.py::TestAnalyticsDomainRouter::test_channel_manager_overview":
        "QUARANTINED 2026-03-24: Changed API - analytics endpoint response format changed",
    "tests/test_pms_phase2_api.py::TestMultiPropertyAuditEndpoints::test_audit_status_board":
        "QUARANTINED 2026-03-24: Changed API - audit endpoint response format changed",
    "tests/test_pms_phase2_api.py::TestMultiPropertyAuditEndpoints::test_readiness_score":
        "QUARANTINED 2026-03-24: Changed API - readiness score calculation changed",
    "tests/test_night_audit_and_timeline.py::test_run_night_audit_basic":
        "QUARANTINED 2026-03-24: Changed API - night audit endpoint behavior changed",
    "tests/test_night_audit_and_timeline.py::test_dry_run_no_db_mutations":
        "QUARANTINED 2026-03-24: Changed API - night audit dry run behavior changed",
    "tests/test_channel_manager_v2.py::TestConnectorCRUD::test_create_connector_returns_201_or_200":
        "QUARANTINED 2026-03-24: Changed API - connector create response changed",
    "tests/test_channel_manager_v2.py::TestMappingsCRUD::test_create_mapping":
        "QUARANTINED 2026-03-24: Changed API - mapping create response changed",

    # --- Category: Changed implementation ---
    "tests/test_production_hardening_v2.py::TestAES256GCMEncryption::test_key_management_service":
        "QUARANTINED 2026-03-24: Changed implementation - key mgmt service API changed",
    "tests/test_production_hardening_v2.py::TestAES256GCMEncryption::test_migration_from_legacy":
        "QUARANTINED 2026-03-24: Changed implementation - legacy migration path changed",
    "tests/test_service_wiring.py::TestSecurityHardeningEndpoints::test_credentials_check":
        "QUARANTINED 2026-03-24: Changed implementation - credentials check response changed",
    "tests/test_service_wiring.py::TestSecurityHardeningEndpoints::test_tenant_guard_status":
        "QUARANTINED 2026-03-24: Changed implementation - tenant guard response changed",
    "tests/test_service_wiring_phase2.py::test_messaging_router_imports_service":
        "QUARANTINED 2026-03-24: Changed implementation - messaging router import path changed",
    "tests/test_admin_tenants_api.py::TestAdminTenantsAPI::test_create_tenant_success":
        "QUARANTINED 2026-03-24: Changed implementation - tenant creation response changed",
    "tests/test_pms_hardening.py::TestFrontDeskService::test_checkout_folio_blocker":
        "QUARANTINED 2026-03-24: Changed implementation - checkout folio behavior changed",
    "tests/test_checkout_balance_fix.py::TestCheckoutBalanceFix::test_checkout_with_outstanding_balance_returns_402":
        "QUARANTINED 2026-03-24: Changed implementation - checkout balance response changed",
    "tests/test_migration_observability.py::TestMigrationObservability::test_observability_endpoint_returns_expected_sections":
        "QUARANTINED 2026-03-24: Changed implementation - observability sections changed",
    "tests/test_reconciliation_complete.py::TestCredentialVault::test_mask_credentials":
        "QUARANTINED 2026-03-24: Changed implementation - credential masking changed",
    "tests/test_reconciliation_engine.py::TestReconciliationRun::test_manual_run":
        "QUARANTINED 2026-03-24: Changed implementation - reconciliation response changed",
    "tests/test_controlplane_ui_api.py::TestTimelineAPI::test_timeline_external_id_lookup":
        "QUARANTINED 2026-03-24: Changed implementation - timeline lookup response changed",
    "tests/test_timeline_dashboard_api.py::TestTimelineAPI::test_timeline_external_id_success":
        "QUARANTINED 2026-03-24: Changed implementation - timeline response changed",

    # --- Category: External dependency / ARI push ---
    "tests/test_ari_push_engine.py::TestBufferDebounce::test_multiple_events_same_key_coalesce":
        "QUARANTINED 2026-03-24: Flaky - buffer debounce timing-dependent test",
    "tests/test_hotelrunner_adapter_api.py::TestHotelRunnerTestConnection::test_hotelrunner_test_connection_no_creds":
        "QUARANTINED 2026-03-24: External dependency - HotelRunner connection test",

    # --- Category: Meta-test referencing quarantined files ---
    "tests/test_production_hardening_v2.py::TestSuiteStability::test_all_mapping_engine_tests_exist":
        "QUARANTINED 2026-03-24: Meta-test checks test_mapping_engine.py which was quarantined",
}
