import importlib

security = importlib.import_module("core.security")


def test_user_document_cache_keeps_same_legacy_user_id_isolated_by_tenant():
    security._USER_DOC_CACHE.clear()
    try:
        security._user_doc_cache_set("hotel-a:legacy-user", {"tenant_id": "hotel-a", "name": "A"})
        security._user_doc_cache_set("hotel-b:legacy-user", {"tenant_id": "hotel-b", "name": "B"})

        assert security._user_doc_cache_get("hotel-a:legacy-user")["name"] == "A"
        assert security._user_doc_cache_get("hotel-b:legacy-user")["name"] == "B"
    finally:
        security._USER_DOC_CACHE.clear()


def test_user_cache_invalidation_removes_all_tenant_contexts_for_the_user():
    security._USER_DOC_CACHE.clear()
    try:
        security._user_doc_cache_set("hotel-a:legacy-user", {"tenant_id": "hotel-a"})
        security._user_doc_cache_set("hotel-b:legacy-user", {"tenant_id": "hotel-b"})

        security._local_evict_user_doc("legacy-user")

        assert security._user_doc_cache_get("hotel-a:legacy-user") is None
        assert security._user_doc_cache_get("hotel-b:legacy-user") is None
    finally:
        security._USER_DOC_CACHE.clear()
