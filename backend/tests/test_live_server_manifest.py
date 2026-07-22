def test_live_server_manifest_paths_exist():
    from pathlib import Path

    from tests.live_server_manifest import LIVE_SERVER_TESTS

    for relative_path in LIVE_SERVER_TESTS:
        assert Path(relative_path).is_file(), relative_path
