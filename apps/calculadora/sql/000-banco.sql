-- ============================================================================
-- Banco e usuário da calculadora (passo ANTERIOR ao schema).
-- ============================================================================
-- Roda como SUPERUSUÁRIO, contra o banco `postgres`, com psql. É o único passo
-- que não pode ser feito pelo Python do projeto, porque `CREATE DATABASE` exige
-- superusuário e não roda dentro de transação.
--
--     make banco-criar
--
-- Idempotente: rodar de novo não quebra e não muda nada. O `\gexec` é do psql
-- (executa o resultado do SELECT como comando), e existe porque `CREATE
-- DATABASE` não aceita `IF NOT EXISTS` — tentar criar um banco que já existe
-- devolve erro, e o objetivo aqui é poder repetir sem medo.
--
-- A senha segue a convenção desta stack: valor de laboratório, no mesmo arquivo
-- declarativo que já cria os bancos do Backstage, Keycloak e Grafana
-- (infrastructure/postgresql/configmap.yaml). Trocar por Secret é bem-vindo —
-- e vale para os quatro, não só para este.
-- ============================================================================

\set ON_ERROR_STOP on

-- ------------------------------------------------------------------- banco
SELECT 'CREATE DATABASE calculadora'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'calculadora')\gexec

-- ---------------------------------------------------------------- usuário
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'calculadora') THEN
        CREATE ROLE calculadora LOGIN PASSWORD 'calculadora-password';
        RAISE NOTICE 'usuário calculadora criado';
    ELSE
        RAISE NOTICE 'usuário calculadora já existia';
    END IF;
END
$$;

-- O dono do banco é o próprio usuário da aplicação: assim o schema pode ser
-- aplicado pela aplicação (sem superusuário) e a carga não depende de ninguém
-- com privilégio a mais.
ALTER DATABASE calculadora OWNER TO calculadora;
GRANT ALL PRIVILEGES ON DATABASE calculadora TO calculadora;
