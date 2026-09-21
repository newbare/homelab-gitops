# F2 — os preços no PostgreSQL (o motor agnóstico)

Fase 2 de 8 do [plano](01-plano.md). A F1 provou que o preço da calculadora
oficial e o do Bulk Price List são **o mesmo número** (10.150 rateCodes iguais,
0 divergentes). Esta fase guarda esse preço num banco, do qual o motor vai
precificar **qualquer** serviço — e não só os 10 itens da vitrine.

---

## A arquitetura, em um desenho

```
fontes oficiais (AWS)                        dado versionado no repositório
  ├─ manifest .......... 440 serviços
  ├─ definição ......... campos do formulário                        (F3)
  ├─ mapas de preço .... rateCode + price        calculator.aws (gzip)
  ├─ Price List ........ unidade + descrição     por rateCode
  └─ correspondência ... família → offerCode  ◄── dados/correspondencia.json
                                                        (confirmada na F1 por
                                                         INTERSECÇÃO de rateCode)
          │
          │  (1) COLETA — carregar_precos.py fala com api/oficial.py
          │      cache em disco · gzip tratado · 103 nós do escopo → 53 mapas
          │      16.402 entradas · 47 mapas sem eixo de região (formato `-calc`)
          ▼
  ══════════ PORTÃO · avaliar_portao() — FUNÇÃO PURA, testada sem banco ══════════
      recusa a carga INTEIRA, sem tocar na base, quando:
        • publicação sem data legível ....... não se sabe DE QUANDO é o preço
        • rateCode vigente desapareceu ...... a dimensão que já usávamos saiu
        • mesmo rateCode, preço ≠ 2 mapas ... a própria oficial se contradiz
        • mesmo rateCode, valor ≠ Price List as duas fontes discordam
      ────────────────────────────────────────────────────────────────────────
      ausência no Price List = AVISO, nunca recusa (142 medidos, irredutíveis)
          │
          ▼  aprovado
  (2) CONSOLIDAÇÃO — o rateCode é a identidade da DIMENSÃO, não do mapa
      16.402 entradas → 8.726 rateCodes únicos
      (quase metade é o MESMO rateCode em mais de um mapa; quem declara
       cada um vai em `atributos.mapas`)
          │
          ▼
  (3) GRAVAÇÃO — UMA transação: ou entra tudo, ou a base fica como estava

      servidor postgresql-0 (um só) · database `calculadora` · schema `public`
      ──────────────────────────────────────────────────────────────────
        mapa_preco     hash do conteúdo → "sem novidade" sem regravar
        preco          vigente | histórico — NUNCA apagado
        carga_log      o que a carga fez  E  o que ela RECUSOU
        servico        catálogo do manifest (440, com o pai resolvido)
        regiao         código (us-east-1) ↔ rótulo (US East (N. Virginia))
        item_detalhe   rate_code + preço usados NO CÁLCULO — a procedência
      ──────────────────────────────────────────────────────────────────
          │
          ▼
      o motor agnóstico: formulário gerado da definição (F3) e cálculo com
      fórmula NOSSA, conferida contra a oficial (F4) — o que a vitrine de
      10 itens não fazia.
```

### Onde cada passo roda

```
  no cluster (reconciliado pelo Argo)
    Job `postgresql-garantir-bancos`  → garante os bancos e usuários
         tolera o "já existe" e VERIFICA no fim: se faltar algo, o Job falha
         dizendo o nome do que faltou
    StatefulSet postgresql + PVC      → onde o dado mora
    (o app da calculadora ainda serve o snapshot JSON; passa a ler o banco
     em F3/F4, quando ganhar credencial no seu próprio namespace)

  no host de operação (esta máquina)
    make banco-bg   → port-forward 127.0.0.1:5432
    make schema     → aplica o 001-schema.sql (idempotente)
    make carga      → coleta, confere no portão e grava
```

---

## 1. Como rodar (um comando)

```bash
cd apps/calculadora
make f2
```

Isso faz, em ordem:

| passo | o que faz | por quê nesta ordem |
|---|---|---|
| `banco-bg` | encaminha a porta 5432 do cluster para `127.0.0.1` | o PostgreSQL não é exposto fora do cluster |
| `banco-criar` | cria o banco e o usuário `calculadora` | `CREATE DATABASE` exige superusuário |
| `schema` | aplica `sql/001-schema.sql` | as tabelas precisam existir antes da carga |
| `carga` | baixa os mapas oficiais e grava os preços | o passo que enche a base |
| `carga-conferir` | mostra o que está na base | a conferência da fase |
| `banco-parar` | derruba o encaminhamento | não deixa porta aberta para trás |

Passo a passo, se preferir ver cada um:

```bash
make banco-bg        # deixa o encaminhamento aberto
make banco-criar     # banco + usuário (idempotente)
make schema          # tabelas (idempotente)
make carga-seca      # coleta e CONFERE, sem gravar nada
make carga           # grava
make carga-conferir  # o que ficou na base
make banco-parar
```

---

## 2. Como se verifica que funcionou

### 2.1 Resultado da carga (executada em 2026-09-20)

```
  catálogo: 440 serviços · escopo: 103 nós
  mapas com preço nesta região: 53 (16402 rateCodes)
  mapas sem eixo de região: 47 (formato `-calc`, não é falha)
  unidades/descrições obtidas para 13495 rateCodes
  conferidos: 18566 iguais · 0 divergentes · 142 ausentes no Price List
  gravados: 8726 preços em 53 mapas
```

⚠️ Esses 47 mapas `-calc` **não são um formato sem região** — foi o que eu supus na
F1. A investigação da definição ([03](03-anatomia-da-definicao.md)) mostrou que a
oferta deles vive num caminho **por região**, sob um `calc-id`:
`.../meteredUnitMaps/<família>/USD/current/<calc-id>/<região>/…`. A classificação
"sem eixo de região" continua correta **para o arquivo que eu baixei**; o que muda
é que agora sei o que esses arquivos são.

E na base:

```
  preços vigentes: 8726
  cloudwatch      152  pub=2026-09-18 14:21:58+00
  eks            1201  pub=2026-09-18 16:42:36+00
  lambda          553  pub=2026-09-19 00:23:59+00
  ...
  preços históricos (nunca apagados): 0
```

Duas leituras que os números exigem, para não parecerem o que não são:

- **16.402 entradas nos mapas viram 8.726 rateCodes únicos.** Quase metade é o
  MESMO rateCode declarado por mais de um mapa (ver §3.5). O número que vale é
  o único — é ele que a calculadora pode precificar.
- **As contagens da conferência são POR SERVIÇO e têm repetição**: o mapa do
  `cloudwatch`, por exemplo, é declarado pelo RDS e pelo EC2, então o mesmo
  rateCode é conferido mais de uma vez. Diferente da F1, que conferiu 10.150 nas
  33 raízes; aqui são 18.566 nos 103 nós (raízes + filhos).

Rodar a carga de novo **não regrava**:

```
  nada novo: todos os mapas desta região já estão carregados
  resultado ................. sem_novidade
```

O `carga_log` registra essa tentativa também — "sem novidade" é resultado
auditável, e não um botão que parece não ter funcionado.

---

## 2.2 O que AINDA é um passo manual (e o que já não é)

O database **não** é criado à mão. Há três níveis, e vale saber qual é qual:

| o quê | como | quando roda |
|---|---|---|
| database + usuário | `infrastructure/postgresql/init-job.yaml` — Job reconciliado pelo Argo | em todo cluster, inclusive num que já existe |
| database + usuário (volume novo) | `configmap.yaml` → `docker-entrypoint-initdb.d` | só na PRIMEIRA inicialização do volume |
| tabelas | `make schema` (o Python aplica o `001-schema.sql`) | quando se quiser; é idempotente |
| preços | `make carga` | quando se quiser (é o botão da F5) |

O `make banco-criar` continua existindo para uso local e para cluster que ainda
não tem o Job. Mas o caminho declarativo é o Job: ele roda o **mesmo**
`create-databases.sql`, tolera o "já existe" e **verifica** o resultado — se um
banco ou usuário faltar, o Job falha com o nome do que faltou.

A lista de bancos existe num lugar só (o ConfigMap). Reescrever o SQL dentro do
Job seria mais "limpo" de ler e mais sujo de manter: duas listas que divergem.

O que ainda **não** é declarativo: as tabelas e a carga de preços. Aplicar o
schema pelo próprio Pod, na subida, é o passo natural — e depende de o app passar
a usar o banco de verdade (F3/F4), que é quando ele ganha credencial no seu
namespace.

---

### 2.3 Onde o dado mora: um servidor, vários databases

Vocabulário primeiro, porque em português "banco" serve para duas coisas — e essa
sobreposição já confundiu a leitura deste documento:

```
servidor (a instância PostgreSQL)   postgresql-0 · imagem postgres:17-alpine · 1 PVC
  └─ database                       o que CREATE DATABASE cria; a conexão aponta para UM
       └─ schema                     `public` — já nasce em todo database novo
            └─ tabela                preco, mapa_preco, carga_log, ...
```

Medido no cluster em 2026-09-20:

```
statefulset.apps/postgresql   1/1          ← UM servidor
pod/postgresql-0              1/1          ← UM processo
pvc data-postgresql-0         10Gi RWO     ← UM volume

backstage             | backstage   | 7526 kB
backstage_plugin_app  | backstage   |   17 MB   ← 13 databases que o Backstage criou
...                     (mais 12 backstage_plugin_*)
calculadora           | calculadora |   14 MB   ← o que esta fase criou
grafana               | grafana     | 7361 kB
keycloak              | keycloak    |   12 MB
postgres              | postgres    | 7518 kB
```

**18 databases no mesmo servidor, e nenhum servidor novo criado.** As tabelas
deste projeto vivem em `calculadora` → schema `public` (11 tabelas).

#### Por que database, e não um schema

Não é escolha nova desta fase: o `create-databases.sql` já criava `backstage`,
`keycloak` e `grafana` como databases separados — e o Backstage confirma a
convenção criando **um database por plugin** (os 13 `backstage_plugin_*`).

| | database separado | schema separado |
|---|---|---|
| dono e permissões | independentes | compartilhados |
| backup / restore | por aplicação | tudo junto |
| nome de tabela repetido | não colide | pode colidir |
| JOIN entre aplicações | **não dá** | dá |

Nenhuma aplicação aqui precisa de JOIN com as tabelas das outras, e o isolamento
compensa: juntar num database só acoplaria o ciclo de vida dos nossos dados ao do
Backstage, e misturaria o dono.

#### O nome do arquivo

`sql/000-banco.sql` cria o **database** — o nome ficou "banco" por ser o
vocabulário corrente em português. O servidor já existia; o que o arquivo faz é
`CREATE DATABASE calculadora`, o usuário dono e o `GRANT`.

#### Por que o Job confere 4 databases, e não os 18

O Job verifica o que a **infraestrutura declara**: os 4 databases e 4 usuários do
`configmap.yaml`. Os 13 `backstage_plugin_*` são criados pelo Backstage em tempo de
execução — conferi-los deixaria o Job vermelho à toa toda vez que um plugin novo
fosse instalado. Verificar o que se declara é diferente de verificar o que os
outros criam por conta própria.

---

## 3. O que foi construído, e por que assim

```bash
make carga-conferir
```

Deve mostrar o total de preços vigentes, quebrado por família, com a data de
publicação de cada mapa — e as últimas cargas com o resultado de cada uma.

O número a conferir: a soma dos `rateCodes` dos mapas da região. O log da carga
imprime essa soma antes de gravar (`mapas com preço nesta região: N (M
rateCodes)`), e o esperado é **~10.236** (os 10.150 conferidos na F1 mais os 86
irredutíveis do Redshift).

```bash
make carga-seca
```

Coleta tudo, roda o portão e informa o que faria — sem tocar na base. É o mesmo
caminho da carga real, com o freio de mão puxado.

```bash
make teste
```

A suíte cobre o portão, a conta do SCRAM (contra o vetor do RFC 7677), a
codificação das mensagens do protocolo e a montagem do log de carga — tudo sem
banco e sem rede. O que exige banco de verdade é a carga a seco, de propósito:
erro de **regra** pega no teste, erro de **fiação** pega na carga.

---

## 3. O que foi construído, e por que assim

### 3.1 `api/pg.py` — cliente PostgreSQL em biblioteca padrão

O projeto tem uma restrição explícita e anterior a esta fase: a aplicação roda
em **imagem oficial do Python + arquivos de ConfigMap**, sem `pip install`, sem
Dockerfile, sem registry. Não existe `psycopg` nesse mundo, e adicioná-lo
obrigaria a construir imagem própria — mudança de arquitetura para atender o
banco, quando o banco é que deve caber na arquitetura.

Então o cliente foi escrito à mão: protocolo v3, autenticação **SCRAM-SHA-256**
(o PostgreSQL 17 não aceita mais MD5 por padrão), protocolo estendido com
parâmetro de verdade (`$1`, `$2` — nunca SQL montado por concatenação) e
protocolo simples para DDL de vários comandos.

Um detalhe que o teste contra o banco real pegou, e que vale registrar: a
primeira versão levantava a exceção no instante em que via o `ErrorResponse`,
deixando no soquete o `ReadyForQuery` que o servidor manda logo depois. A
conexão ficava **dessincronizada** — a leitura seguinte devolvia a mensagem
atrasada, e o sintoma era "consulta sem linhas" num lugar do código sem relação
com o erro. Sem o conserto, qualquer erro inutilizaria a conexão, e a transação
com ROLLBACK (a regra do projeto) não funcionaria.

### 3.2 `sql/001-schema.sql` — o modelo, e as duas regras que ele obedece

**Nada de preço é apagado.** A carga nova marca os anteriores como histórico
(`vigente = false`). É o que permite responder depois "por que o mês passado deu
outro número?" — a lição `orig`/`latest` do ISU-HPC. O que garante isso sem
permitir dois vigentes ao mesmo tempo é um **índice único parcial**
(`UNIQUE (rate_code, regiao_codigo) WHERE vigente`).

**Todo número tem procedência.** O total de um item é a soma das linhas de
`item_detalhe`, e cada linha carrega o `rate_code` e o preço unitário usados no
momento do cálculo. Se o preço mudar depois, a estimativa antiga continua
explicando a si mesma.

### 3.3 `carregar_precos.py` — a carga, com portão

Baixa o **mapa inteiro** de cada serviço do escopo (10 mil rateCodes, não 10
itens) e grava. As decisões que ele toma, e as que ele **se recusa** a tomar:

| situação | o que faz | por quê |
|---|---|---|
| publicação sem data legível | **recusa** | não se sabe DE QUANDO é o preço que entrou |
| família que tinha preço e não veio | **recusa** | o silêncio deixaria preço velho no ar como se fosse atual |
| rateCode vigente desapareceu do mapa | **recusa** | a dimensão que já usamos deixou de ser publicada |
| **mesmo** rateCode com valor diferente entre as duas fontes | **recusa** | as duas discordam; escolher uma seria adivinhar |
| rateCode ausente no Bulk Price List | avisa | os 86 do Redshift são medidos e **irredutíveis** |
| mapa sem eixo de região (`-calc`) | conta à parte | é outro formato de mapa, não falta de região |
| hash do conteúdo já carregado | encerra "sem novidade" | não regrava o que não mudou |

A regra que decide tudo isso é `avaliar_portao`, **função pura** — recebe dado,
devolve recusas. Regra que só se testa com banco de pé é regra que quase nunca é
testada.

### 3.4 Unidade e descrição: de onde vêm

O mapa da calculadora traz **`rateCode` e `price`, e nada mais**. A unidade não
está lá — e sem unidade não se sabe que `Hrs` multiplica por hora e que `GB-Mo`
precisa ser pro-rateado. A unidade vem do Bulk Price List, casada pelo **mesmo
`rateCode`** (é o que a F1 provou que funciona).

O arquivo do EC2 em us-east-1 tem centenas de MB, então há um limite explícito
(`--limite-mb`, padrão 80) e o tamanho é consultado por `HEAD` **antes** do
download. O que for pulado é **reportado** — preferir unidade ausente (visível) a
travar a carga inteira por causa de um arquivo gigante (invisível).

### 3.5 ⚠️ Um rateCode pode ser declarado por MAIS DE UM mapa

Descoberto na primeira carga de verdade, e **não** deduzido: `redshift` e
`redshift-storage` publicam os **mesmos** 140 rateCodes, e o `cloudwatch` aparece
no mapa do RDS e no do EC2. Consequência medida: **16.402 entradas viram 8.726
rateCodes únicos**.

O rateCode é a identidade da dimensão, então o **preço é um só** — o que muda é
quem o declara. A primeira versão gravava uma linha por `(mapa, rateCode)` e o
índice único parcial recusou a segunda com `23505`. O índice estava certo; o
erro era meu, e a transação reverteu sem deixar resíduo.

O modelo ficou assim:

- a linha de preço é única por `(rate_code, regiao_codigo)` — como o plano dizia;
- os mapas que a declaram vão em `atributos.mapas`;
- **a demolição do vigente é por rateCode** (via tabela temporária com os que vão
  entrar), e não por família: a linha vigente está ligada a UM mapa, e marcar por
  família deixaria vigente o rateCode cujo mapa de origem não viesse nesta carga —
  o que estouraria o índice numa chave duplicada;
- **o mesmo rateCode com preço diferente em dois mapas é RECUSA.** As publicações
  da própria oficial discordando é sinal de que uma mudou de forma, e escolher
  uma delas seria adivinhar.

---

## 4. O que AINDA não está feito

- **Uma região só.** A carga carrega `us-east-1` / `US East (N. Virginia)`, o
  par que está em `dados/escopo.json`. A tradução `código ↔ rótulo` para as
  outras regiões é trabalho da F6.
- **`campo_servico` está vazia.** A tabela existe; quem a preenche é o leitor de
  definição da F3.
- **A fórmula continua em aberto.** Tenho as dimensões e os preços; **não** tenho
  a aritmética que os combina. Cada serviço terá a fórmula nossa, documentada e
  testada contra a oficial (F4).
- **O agrupamento por categoria (D8) segue sem origem conhecida.** Não está no
  manifest, e não vai ser inventado.
- **2 rateCodes ficaram sem unidade**: os do mapa do EC2 (o arquivo de 459 MB que
  o limite de 80 MB pula). Unidade ausente é visível; travar a carga inteira por
  causa de um arquivo gigante seria invisível.

---

## 5. Arquivos desta fase

```
api/pg.py               cliente PostgreSQL em biblioteca padrão (SCRAM-SHA-256)
sql/000-banco.sql       banco + usuário calculadora (exige superusuário, via psql)
sql/001-schema.sql      o modelo (idempotente, aplicado pelo Python)
carregar_precos.py      a carga, com o portão de validação
tests/test_pg.py        SCRAM contra o RFC 7677, quadro das mensagens, erros
tests/test_carga.py     o portão, os derivados do rateCode, o lote, o log
```

Alvos novos do `make`: `f2`, `banco-bg`, `banco-forward`, `banco-parar`,
`banco-criar`, `schema`, `carga-seca`, `carga`, `carga-conferir`, `teste-pg`,
`teste-carga`.
