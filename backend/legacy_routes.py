"""
Legacy Routes — DEPRECATED

Phase B: Domain Module Separation COMPLETE
Phase C/D/E: Hardening phases IMPLEMENTED

All endpoint definitions have been extracted into domain-specific routers
under backend/domains/. This file is retained as a minimal backward-compatibility
shim. It contains NO endpoints.

api_router is now created directly in server.py.
All inline Pydantic models have been superseded by definitions in the
domain router files themselves.

This file will be removed in a future cleanup pass.
"""
from fastapi import APIRouter

# Backward compatibility — some modules may still import api_router
api_router = APIRouter(prefix="/api")
