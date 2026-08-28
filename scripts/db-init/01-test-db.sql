-- Executed by the postgres image on first start of an empty volume.
-- The test database is separate from the dev database on purpose: tests/conftest.py
-- creates and drops the schema per session, and a shared database would let a test run
-- wipe development data (Day 1 design.md Decision 12).
CREATE DATABASE nutrition_test OWNER nutrition;
