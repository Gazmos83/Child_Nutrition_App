"""Child Nutrition AI App backend.

Layout keeps HTTP, domain, and (later) AI concerns separable:

- ``core``    application configuration and cross-cutting concerns
- ``db``      SQLAlchemy engine, session management, declarative base
- ``models``  ORM models and the controlled vocabularies they use
- ``schemas`` Pydantic request/response contracts
- ``api``     FastAPI routers -- HTTP concerns only, no domain logic
"""
