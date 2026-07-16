"""Bazi backend package.

Domain layer (app.domain) MUST NOT import from web/db/LLM SDKs.
Adapters (app.adapters) wrap external systems.
Application services (app.services) compose them.
API (app.api) exposes HTTP/JSON; jobs (app.jobs) drives async work.
"""
__version__ = "0.1.0"