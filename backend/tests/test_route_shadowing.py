"""Task #133 — CI guard: catch hidden URL conflicts that silently break admin screens.

FastAPI matches routes in **declaration order**. If a router declares a
dynamic-prefix route (e.g. ``GET /api/checkin/online/{booking_id}``) and
later — in the SAME app — declares a static sibling under the same prefix
(e.g. ``GET /api/checkin/online/id-photos``), the dynamic route always
wins: the static endpoint is silently unreachable. The handler under the
dynamic route gets called with the static path segment as the path
parameter (booking_id="id-photos"), and the staff-facing list call ends
up returning the guest check-in payload instead. There is no error, no
log, and no exception — just a blank admin screen in production.

The original Task #123 e2e suite caught one such case in
``backend/domains/guest/checkin_router.py``; manual code review later
found the same shape twice more (HR payroll export, channel manager
lineage stats). This test loads the real FastAPI app, walks the route
table in declaration order, and fails the build if **any** static route
is shadowed by an earlier dynamic sibling at the same HTTP method.

When this test fails, the message names BOTH the offending dynamic route
(declared earlier) and the shadowed static route (declared later), so
the fix is mechanical: move the static route above the dynamic one.

Mounted sub-apps (``starlette.routing.Mount``) are skipped — their
internal routes are owned by a different router and resolved via the
mount's own match logic, not the parent app's declaration order.
"""
from __future__ import annotations

import pytest
from fastapi.routing import APIRoute


def _is_dynamic(path: str) -> bool:
    """A path is dynamic if it contains a FastAPI path placeholder ``{x}``."""
    return "{" in path and "}" in path


def _find_shadowed_routes(app) -> list[tuple[str, str, str, str]]:
    """Return ``(method, dynamic_path, dynamic_endpoint, static_path)`` for
    every static route that is unreachable because an earlier dynamic
    sibling at the same HTTP method matches the same path.

    The check is intentionally narrow: it only flags STATIC routes
    (``/foo/bar``) that an earlier DYNAMIC route (``/foo/{x}``) would
    swallow. Two dynamic routes that overlap (``/foo/{x}`` vs
    ``/foo/{y}/baz``) are out of scope — those are typically intentional
    and FastAPI's longest-prefix match resolves them correctly.
    """
    api_routes = [r for r in app.routes if isinstance(r, APIRoute)]
    shadowed: list[tuple[str, str, str, str]] = []

    for i, route in enumerate(api_routes):
        if _is_dynamic(route.path):
            continue  # only static routes can be silently shadowed
        if not route.methods:
            continue
        for earlier in api_routes[:i]:
            if not _is_dynamic(earlier.path):
                continue
            shared_methods = earlier.methods & route.methods
            if not shared_methods:
                continue
            # ``path_regex`` is a compiled regex provided by Starlette that
            # matches the exact path the route would dispatch on. If the
            # earlier dynamic route's regex matches our static path, the
            # static route is unreachable for that method.
            if earlier.path_regex.match(route.path):
                for method in sorted(shared_methods):
                    shadowed.append(
                        (
                            method,
                            earlier.path,
                            getattr(earlier.endpoint, "__qualname__", repr(earlier.endpoint)),
                            route.path,
                        )
                    )
    return shadowed


@pytest.fixture(scope="module")
def app():
    """Load the real FastAPI app (the one uvicorn serves)."""
    import importlib

    mod = importlib.import_module("server")
    return mod.app


def test_no_static_route_is_shadowed_by_earlier_dynamic_sibling(app):
    """No static route may be silently swallowed by an earlier dynamic route.

    The original Task #123 finding:
        GET /api/checkin/online/{booking_id}   (declared first, dynamic)
        GET /api/checkin/online/id-photos      (declared later, static)

    The list call returned the guest check-in status payload instead of
    the staff list — the entire admin screen was broken in production
    with no error and no log. This guard turns that class of bug into a
    build-time failure naming both routes.

    To fix a failure: move the shadowed STATIC route above the
    SHADOWING DYNAMIC route in the same router file. Adding a comment
    that pins the order (see ``checkin_router.py`` for the canonical
    example) is strongly recommended so future edits do not regress.
    """
    shadowed = _find_shadowed_routes(app)
    if not shadowed:
        return

    lines = [
        f"Found {len(shadowed)} static route(s) silently shadowed by an "
        "earlier dynamic sibling. FastAPI matches routes in declaration "
        "order, so each shadowed STATIC route below is unreachable — "
        "every request lands on the DYNAMIC handler with the static "
        "segment as the path parameter (e.g. `id` = 'export'). Fix by "
        "moving the static route ABOVE the dynamic one in its router "
        "file.",
        "",
    ]
    for method, dyn_path, dyn_endpoint, static_path in shadowed:
        lines.append(
            f"  [{method}] {static_path}\n"
            f"        ↑ shadowed by earlier dynamic route\n"
            f"          {dyn_path}   →   {dyn_endpoint}"
        )
    pytest.fail("\n".join(lines))


def test_route_shadowing_detector_catches_synthetic_regression():
    """Self-test: the detector must catch the original Task #123 shape.

    We build a tiny throwaway FastAPI app that reproduces the exact
    pattern that broke production (dynamic route declared before a
    static sibling under the same prefix), then assert the detector
    flags it. This protects the detector itself: if someone weakens
    ``_find_shadowed_routes`` so the real check passes vacuously, this
    test fails immediately.
    """
    from fastapi import FastAPI

    decoy = FastAPI()

    @decoy.get("/api/checkin/online/{booking_id}")
    async def _status(booking_id: str):  # pragma: no cover - never called
        return {"completed": False}

    @decoy.get("/api/checkin/online/id-photos")
    async def _list():  # pragma: no cover - never called
        return {"items": []}

    found = _find_shadowed_routes(decoy)
    assert any(
        method == "GET"
        and dyn_path == "/api/checkin/online/{booking_id}"
        and static_path == "/api/checkin/online/id-photos"
        for method, dyn_path, _endpoint, static_path in found
    ), (
        "Route-shadowing detector regressed: it must flag the original "
        f"Task #123 pattern but reported {found!r}."
    )


def test_route_shadowing_detector_ignores_non_overlapping_methods():
    """Detector must NOT flag a dynamic GET vs a static POST at the same path.

    This is a common, intentional pattern (``GET /resource/{id}`` for
    fetch + ``POST /resource/bulk-delete`` for admin action). If the
    detector flagged this, every router in the codebase would explode
    with false positives.
    """
    from fastapi import FastAPI

    decoy = FastAPI()

    @decoy.get("/resource/{id}")
    async def _get(id: str):  # pragma: no cover - never called
        return {"id": id}

    @decoy.post("/resource/bulk-delete")
    async def _bulk():  # pragma: no cover - never called
        return {"deleted": 0}

    assert _find_shadowed_routes(decoy) == [], (
        "False positive: a dynamic GET must not be reported as shadowing "
        "a static POST at the same path."
    )
