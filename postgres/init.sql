-- =====================================================================
-- init.sql - Postgres bootstrap for LNBits
-- OpenSplit Infrastructure (Phase 1)
-- =====================================================================
--
-- LNBits will create its own schema/tables on first start, but we make
-- sure the database, role and a dedicated schema exist with the right
-- privileges. This script is executed automatically by the official
-- postgres image on first boot (everything in /docker-entrypoint-initdb.d/).
-- =====================================================================

-- Make sure the LNBits role can create everything it needs.
ALTER ROLE lnbits WITH CREATEDB;

-- Dedicated schema (LNBits defaults to "public", but having an explicit
-- one makes future migrations and backups cleaner).
CREATE SCHEMA IF NOT EXISTS lnbits AUTHORIZATION lnbits;

-- Grant full privileges on the database to the LNBits role.
GRANT ALL PRIVILEGES ON DATABASE lnbits TO lnbits;
GRANT ALL PRIVILEGES ON SCHEMA public  TO lnbits;
GRANT ALL PRIVILEGES ON SCHEMA lnbits  TO lnbits;

-- Useful extensions.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =====================================================================
-- Orchestrator database
-- =====================================================================
-- The orchestrator service connects to a dedicated "orchestrator" database
-- (see ORCHESTRATOR_DB_URL in docker-compose.yml). The official postgres
-- image only creates POSTGRES_DB (lnbits) on first boot, so we create the
-- orchestrator database here on clean init. CREATE DATABASE cannot run in a
-- transaction or use IF NOT EXISTS, so guard it with \gexec.
SELECT 'CREATE DATABASE orchestrator OWNER lnbits'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'orchestrator')\gexec
