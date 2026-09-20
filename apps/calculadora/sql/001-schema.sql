-- ============================================================================
-- Calculadora Resilience — schema do banco de preços e estimativas
-- ============================================================================
-- Fase F2 do plano (docs/calculadora/01-plano.md, secao 4).
--
-- Por que este arquivo existe como SQL, e nao como codigo Python
-- =================================================================
-- Porque o schema e um ARTEFATO, e nao um efeito colateral do programa. Assim
-- ele pode ser lido, revisado e aplicado com `psql` por quem nao le Python -- e
-- a mesma carga roda em outro banco sem que ninguem precise abrir o codigo.
--
-- Idempotente de proposito: aplicar duas vezes nao quebra e nao apaga nada.
-- (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`.)
--
-- AS DUAS REGRAS QUE O DESENHO OBEDECE
-- ====================================
-- 1. NADA DE PRECO E APAGADO. Preco antigo vira HISTORICO (`vigente = false`),
--    porque e o unico jeito de responder depois "por que o mes passado deu
--    outro numero?". A coluna `vigente` e o que permite isso sem perder a
--    linha antiga -- e o indice unico parcial (`WHERE vigente`) garante que
--    exista UM preco vigente por rate_code/regiao, sem proibir os historicos.
--
-- 2. TODO NUMERO TEM PROCEDENCIA. Cada linha de custo em `item_detalhe` guarda
--    o `rate_code` e o `preco_unitario` que foram usados NO MOMENTO do calculo.
--    Se o preco mudar depois, a estimativa antiga continua explicando a si
--    mesma -- e nao passa a ser um numero orfao.
--
-- Aviso sobre `servico` x `campo_servico`
-- =======================================
-- As duas descrevem o que a AWS publica: `servico` vem do manifest (440
-- entradas) e `campo_servico`, da definicao de cada servico. Elas sao o
-- CATALOGO, e nao configuracao nossa -- por isso guardam `visto_em` e a versao
-- da definicao: quando a AWS mudar, da para ver o que mudou, e nao so que
-- "esta diferente".
-- ============================================================================

-- ------------------------------------------------------------------ catalogo
CREATE TABLE IF NOT EXISTS servico (
    id                  BIGSERIAL PRIMARY KEY,
    service_code        TEXT NOT NULL UNIQUE,
    nome                TEXT,
    descricao           TEXT,
    sub_tipo            TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    definition_url      TEXT,
    -- Hierarquia do manifest: `subServiceSelector` (pai) declara os filhos em
    -- `templates`. O pai NAO tem preco proprio, quem precifica sao os filhos.
    parent_service_code TEXT,
    visto_em            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS servico_pai_idx ON servico (parent_service_code);

-- ---------------------------------------------------------------- formulario
-- Os campos do formulario de cada servico, lidos da definicao oficial. E o
-- que permite NAO escrever 24 formularios a mao: o formulario e dado.
CREATE TABLE IF NOT EXISTS campo_servico (
    id                 BIGSERIAL PRIMARY KEY,
    service_code       TEXT NOT NULL REFERENCES servico (service_code) ON DELETE CASCADE,
    campo_id           TEXT NOT NULL,
    tipo               TEXT,
    sub_tipo           TEXT,
    rotulo             TEXT,
    opcoes             JSONB,
    obrigatorio        BOOLEAN NOT NULL DEFAULT FALSE,
    ordem              INTEGER NOT NULL DEFAULT 0,
    -- Versao da definicao (`version` no JSON da AWS, ex.: 0.0.146). Serve para
    -- detectar formulario desatualizado sem comparar os campos um a um.
    definition_version TEXT,
    visto_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (service_code, campo_id)
);

-- ------------------------------------------------------------------- regiao
-- `codigo` e o vocabulario do Bulk Price List (`us-east-1`).
-- `rotulo` e o vocabulario do mapa da calculadora (`US East (N. Virginia)`).
-- Os dois convivem na mesma linha porque a conferencia por rateCode precisa
-- falar as duas linguas -- e essa traducao e dado, nao adivinhacao no codigo.
CREATE TABLE IF NOT EXISTS regiao (
    id         BIGSERIAL PRIMARY KEY,
    codigo     TEXT NOT NULL UNIQUE,
    rotulo     TEXT UNIQUE,
    disponivel BOOLEAN NOT NULL DEFAULT TRUE,
    visto_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------- carga (mapa)
-- Uma linha por MAPA carregado. O `hash_conteudo` e o que responde "mudou
-- alguma coisa?" sem comparar preco por preco: se o hash ja foi carregado, a
-- carga seguinte encerra como "sem novidade" e nao toca na base.
CREATE TABLE IF NOT EXISTS mapa_preco (
    id             BIGSERIAL PRIMARY KEY,
    familia        TEXT NOT NULL,
    offer_code     TEXT,
    publicacao_em  TIMESTAMPTZ,
    moeda          TEXT NOT NULL DEFAULT 'USD',
    url_origem     TEXT NOT NULL,
    hash_conteudo  TEXT NOT NULL UNIQUE,
    carregado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    carregado_por  TEXT
);

CREATE INDEX IF NOT EXISTS mapa_preco_familia_idx ON mapa_preco (familia);

-- -------------------------------------------------------------------- preco
-- ⚠️ Um rateCode pode ser declarado por MAIS DE UM mapa da oficial (medido:
-- `redshift` e `redshift-storage` publicam os mesmos 140 rateCodes; o
-- `cloudwatch` aparece no mapa do RDS e no do EC2). O rateCode é a identidade da
-- DIMENSÃO, então o preço é uma linha só — e os mapas que o declaram vão em
-- `atributos.mapas`. Por isso a família não entra na chave única: ela descreveria
-- um mapa, e não a dimensão.
CREATE TABLE IF NOT EXISTS preco (
    id             BIGSERIAL PRIMARY KEY,
    mapa_preco_id  BIGINT NOT NULL REFERENCES mapa_preco (id) ON DELETE RESTRICT,
    rate_code      TEXT NOT NULL,
    sku            TEXT,
    regiao_codigo  TEXT NOT NULL REFERENCES regiao (codigo),
    preco          NUMERIC(20, 10),
    unidade        TEXT,
    descricao      TEXT,
    familia_produto TEXT,
    -- O item cru do mapa oficial, guardado inteiro. E o que permite reprocessar
    -- sem baixar de novo, e o que evita que uma coluna que eu nao previ hoje
    -- signifique dado perdido amanha.
    atributos      JSONB,
    vigente        BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ⚠️ INDICE UNICO PARCIAL. Sem o `WHERE vigente`, o preco historico colidiria
-- com o novo e a carga nao teria como guardar os dois -- que e exatamente o que
-- a regra 1 exige. Com ele, existe UM vigente e quantos historicos forem
-- precisos.
CREATE UNIQUE INDEX IF NOT EXISTS preco_vigente_unico
    ON preco (rate_code, regiao_codigo) WHERE vigente;

CREATE INDEX IF NOT EXISTS preco_rate_code_idx ON preco (rate_code);
CREATE INDEX IF NOT EXISTS preco_mapa_idx ON preco (mapa_preco_id);

-- --------------------------------------------------------------- estimativa
CREATE TABLE IF NOT EXISTS estimativa (
    id            BIGSERIAL PRIMARY KEY,
    nome          TEXT NOT NULL,
    descricao     TEXT,
    regiao_codigo TEXT NOT NULL REFERENCES regiao (codigo),
    janela_horas  NUMERIC(10, 2),
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Grupo hierarquico (pai_id): e o que permite "por servico", "por grupo" e
-- total, do jeito que a oficial mostra.
CREATE TABLE IF NOT EXISTS grupo_estimativa (
    id            BIGSERIAL PRIMARY KEY,
    estimativa_id BIGINT NOT NULL REFERENCES estimativa (id) ON DELETE CASCADE,
    nome          TEXT NOT NULL,
    pai_id        BIGINT REFERENCES grupo_estimativa (id) ON DELETE CASCADE,
    ordem         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS item_estimativa (
    id            BIGSERIAL PRIMARY KEY,
    estimativa_id BIGINT NOT NULL REFERENCES estimativa (id) ON DELETE CASCADE,
    grupo_id      BIGINT REFERENCES grupo_estimativa (id) ON DELETE SET NULL,
    service_code  TEXT NOT NULL,
    -- O que o usuario preencheu, cru. Guardar a ENTRADA (e nao so o total) e o
    -- que permite recalcular depois com preco novo sem pedir tudo de novo.
    entrada       JSONB,
    calculado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    total         NUMERIC(20, 10)
);

CREATE INDEX IF NOT EXISTS item_estimativa_estimativa_idx ON item_estimativa (estimativa_id);

-- ★ O CORACAO DO "NAO E FAKE NEWS"
-- Cada linha de custo aponta o rate_code e o preco unitario usados. O total do
-- item e a soma das linhas, e nao um numero guardado por fora que ninguem
-- consegue abrir.
CREATE TABLE IF NOT EXISTS item_detalhe (
    id             BIGSERIAL PRIMARY KEY,
    item_id        BIGINT NOT NULL REFERENCES item_estimativa (id) ON DELETE CASCADE,
    rate_code      TEXT,
    descricao      TEXT,
    quantidade     NUMERIC(20, 6),
    unidade        TEXT,
    preco_unitario NUMERIC(20, 10),
    subtotal       NUMERIC(20, 10),
    -- Linha que existe mas nao tem preco: fica declarada como LACUNA, e nunca
    -- entra no total como zero. Zero silencioso e a forma mais educada de um
    -- painel mentir.
    sem_preco      BOOLEAN NOT NULL DEFAULT FALSE,
    motivo         TEXT,
    ordem          INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS item_detalhe_item_idx ON item_detalhe (item_id);

-- --------------------------------------------------------------- carga (log)
-- O que o botao de atualizar preco fez -- e o que ele RECUSOU. A coluna
-- `resultado` e o veredito: `ok`, `sem_novidade`, `recusado` ou `erro`.
CREATE TABLE IF NOT EXISTS carga_log (
    id              BIGSERIAL PRIMARY KEY,
    iniciado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    concluido_em    TIMESTAMPTZ,
    duracao_ms      INTEGER,
    resultado       TEXT NOT NULL,
    regiao_codigo   TEXT,
    -- `publicacoes`: a data de publicacao de CADA mapa carregado. E o que
    -- permite dizer "este preco e de 2026-09-18" sem consultar a AWS de novo.
    publicacoes     JSONB,
    mapas           INTEGER NOT NULL DEFAULT 0,
    precos_novos    INTEGER NOT NULL DEFAULT 0,
    precos_historico INTEGER NOT NULL DEFAULT 0,
    verificadas     INTEGER NOT NULL DEFAULT 0,
    divergentes     INTEGER NOT NULL DEFAULT 0,
    ausentes        INTEGER NOT NULL DEFAULT 0,
    mensagem        TEXT,
    executado_por   TEXT
);

CREATE INDEX IF NOT EXISTS carga_log_iniciado_idx ON carga_log (iniciado_em DESC);

-- ------------------------------------------------------------------- views
-- Consulta de apoio: o que esta vigente e de quando. E a primeira pergunta que
-- alguem faz na frente de um numero estranho.
CREATE OR REPLACE VIEW preco_vigente AS
SELECT p.rate_code,
       p.regiao_codigo,
       p.preco,
       p.unidade,
       p.descricao,
       p.familia_produto,
       m.familia,
       m.offer_code,
       m.publicacao_em,
       m.url_origem
FROM preco p
         JOIN mapa_preco m ON m.id = p.mapa_preco_id
WHERE p.vigente;
