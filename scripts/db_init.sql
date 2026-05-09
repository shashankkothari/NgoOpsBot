-- NGO OpsBot — PostgreSQL initialisation script
-- Runs once when the Docker postgres container is first created.
-- Actual schema is managed by Alembic migrations.

-- Ensure the database exists (Docker entrypoint creates it, but this is a safeguard)
-- CREATE DATABASE ngoopsbot;  -- already created by POSTGRES_DB env var

-- Enable UUID generation extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable trigram index support (useful for fuzzy search on names)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable cryptographic functions (pgcrypto) — optional
CREATE EXTENSION IF NOT EXISTS pgcrypto;
