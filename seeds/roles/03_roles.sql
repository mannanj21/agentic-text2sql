-- 03_roles.sql
-- Create read-only and writer roles for testing the agent safety checks.

-- 1. Create the read-only role
CREATE ROLE readonly_demo WITH LOGIN PASSWORD 'readonly_pass';
GRANT USAGE ON SCHEMA public TO readonly_demo;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_demo;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_demo;

-- Restrict read-only role further
ALTER ROLE readonly_demo SET default_transaction_read_only = on;
ALTER ROLE readonly_demo SET statement_timeout = '30s';

-- 2. Create the writer role (used for negative testing)
CREATE ROLE writer_demo WITH LOGIN PASSWORD 'writer_pass';
GRANT USAGE ON SCHEMA public TO writer_demo;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO writer_demo;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO writer_demo;
