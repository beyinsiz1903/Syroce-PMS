"""Shared SlowAPI limiter instance.

Exists as its own module so router files can `from rate_limit import limiter`
without importing server.py (which would cause a circular import: server
imports the routers).
"""
from slowapi import Limiter
from helpers import get_user_or_ip

limiter = Limiter(key_func=get_user_or_ip)
