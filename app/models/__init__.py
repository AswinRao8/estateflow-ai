# models/ owns all data structures for the project.
#
# Current files:
#   base.py    — APIResponse[T] and ErrorResponse (Pydantic envelopes used by all routers)
#   enums.py   — All domain StrEnums: LeadState, IntentType, PropertyType, etc.
#
# Phase 1+ domain files follow this convention:
#   {domain}.py — one file per domain entity containing BOTH the SQLAlchemy ORM class
#                 and the Pydantic DTOs for that domain.
#
#   Example layout inside lead.py:
#     class Lead(Base, TimestampMixin): ...      <- SQLAlchemy ORM model
#     class LeadCreate(BaseModel): ...           <- Pydantic DTO for writes
#     class LeadRead(BaseModel): ...             <- Pydantic DTO for reads
#
# Why co-location:
#   - No circular import risk (ORM model and its schemas live in the same file)
#   - One lookup location for everything about a domain entity
#   - Split only if a domain file grows beyond ~150 lines due to many DTO variants
#
# After adding a domain file, import it in migrations/env.py so Alembic
# can detect its table. Do not import domain models from this __init__.py.
