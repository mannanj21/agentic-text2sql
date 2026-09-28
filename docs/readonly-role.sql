-- Documented Read-Only Role Setup Snippet
-- Customers of the Agentic Text-to-SQL Analytics Platform should run a script
-- similar to this on their database to provision a safe, read-only credential
-- for the application to use.

-- 1. Create a dedicated role
CREATE ROLE text2sql_readonly WITH LOGIN PASSWORD 'YOUR_SECURE_PASSWORD';

-- 2. Grant connection and schema usage
GRANT CONNECT ON DATABASE your_database TO text2sql_readonly;
GRANT USAGE ON SCHEMA public TO text2sql_readonly;

-- 3. Grant SELECT on all existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO text2sql_readonly;

-- 4. Ensure future tables also grant SELECT automatically
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO text2sql_readonly;

-- 5. Force the role to run in read-only transaction mode as an extra safeguard
ALTER ROLE text2sql_readonly SET default_transaction_read_only = on;

-- 6. Set a strict statement timeout to prevent long-running analytical queries from degrading database performance (e.g., 30 seconds)
ALTER ROLE text2sql_readonly SET statement_timeout = '30s';
