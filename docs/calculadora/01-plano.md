# Plano — Calculadora de custo AWS agnóstica

> **Fase:** 2 de 3 (Pesquisa → **Plano** → Implementação)
> **Data:** 2026-09-20
> **Status:** proposta. **Nada implementado.** A Fase 3 começa após aprovação.
> **Substitui:** o `apps/calculadora` atual (vitrine de 13 itens fixos) — ele não
> é descartado como código: vira o primeiro *preset* da calculadora nova.

---

## 1. Evidências verificadas (a pesquisa desta fase)

Tudo abaixo foi conferido em 2026-09-20 contra o artefato real, não contra doc de
terceiro. Fonte e versão ao lado de cada item.

### 1.1 O fluxo da calculadora oficial

`docs.aws.amazon.com/pricing-calculator/latest/userguide/` — índice completo
(`toc-contents.json`) lido em 2026-09-20:

```
1. Escolher o serviço   (N serviços; catálogo, não lista fixa)
2. Configurar           descrição + REGIÃO + campos daquele serviço
3. Agrupar              grupo hierárquico alinhado à arquitetura
4. Ver                  por serviço · por grupo · total
                        upfront + mensal + anual · "ver cálculos" (o porquê do número)
5. Salvar / compartilhar / exportar    link público · CSV · PDF
```

As 4 funcionalidades declaradas: **preço transparente · grupos hierárquicos ·
salvar o link · exportar**. A doc também declara: *"os preços vêm do AWS Price
List API"* — a **mesma fonte que `apps/calculadora/buscar_precos.py` já consome**.

### 1.2 O catálogo é dado, não código

`https://d1qsjq9pzbk1k6.cloudfront.net/manifest/en_US.json` — HTTP 200, 398 KB,
sem credencial, lido em 2026-09-20:

| | |
|---|---|
| Serviços | **440** (434 ativos, 6 inativos) |
| Por serviço | `name` · `serviceCode` · `description` · `searchKeywords` · **`regions`** · `linkUrl` · `isActive` · **`serviceDefinitionLocation`** · `subType` · `templates` · `slug` · `hasDataTransfer` · `bulkImportEnabled` |
| Hierarquia | **34 pais** (`subServiceSelector`) com **238 filhos** (`subService`) · 166 autônomos · 2 `TCOCalculator` |
| Campos de dependência | **não existe** campo `dependencies`. A relação é a árvore pai/filho (`templates`) e a faceta `hasDataTransfer` (55 serviços) |

`serviceDefinitionLocation` é a URL do **formulário** daquele serviço. Exemplo
verificado (`aWSLambda`, 102 KB, versão 0.0.146): 2 templates
(`lambdaWithFreeTier` / `lambdaWithoutFreeTier`), 5 seções, ~42 campos, cada
campo já tipado — `input/dropdown`, `input/frequency`, `input/fileSize`,
`pricing/pricingComboV2`, `pricing/tieredPricing`. **O formulário é dado.**

### 1.3 O preço da oficial é verificável por `rateCode`

Descoberto e conferido nesta fase:

```
mapa de preços:  https://calculator.aws/pricing/2.0/meteredUnitMaps/<família>/USD/current/<família>.json
                 (calculadora.aws — NÃO o CloudFront do manifest; o host errado dá 403)
                 gzip: 632 KB → 2,1 MB; regenerado diariamente; índice por rótulo humano
                 ATENÇÃO: a contagem de regiões é POR MAPA, não uma só: medi 23, 36, 37, 38,
                 40, 42, 106 e 110 em mapas diferentes — "37" era só o Lambda. E as famílias
                 terminadas em `-calc` vêm com `regions` VAZIO: são mapa de outro formato, sem
                 eixo de região, e não "serviço sem região disponível"
cada dimensão:   { "price": "0.0000002000",
                   "rateCode": "ZZQXJMTMJJG6F4RP.JRTCKXETXF.6YS6EN2CT7" }
```

O `rateCode` (`SKU.oferta.versão`) é **a mesma chave do AWS Bulk Price List**.
Resultado da conferência `rateCode` contra `rateCode`, em us-east-1:

| Serviço | offerCode | rateCodes | iguais | diferentes | ausentes |
|---|---|---|---|---|---|
| Lambda | `AWSLambda` | 571 | 571 | 0 | 0 |
| EKS | `AmazonEKS` | 1201 | 1201 | 0 | 0 |
| KMS | `awskms` | 6 | 6 | 0 | 0 |
| Route 53 | `AmazonRoute53` | 12 | 12 | 0 | 0 |

Em todos, a `publicationDate` do mapa oficial é **idêntica** à do Price List.
**Conclusão: mesma fonte, mesma publicação, mesmo número.** A verificação é um
join de dicionário — barata e automatizável.

**Escopo inteiro (24 serviços, 33 nós, filhos descobertos do próprio manifest):**

| medida | valor |
|---|---|
| rateCodes com o **mesmo** valor nas duas fontes | **10.150** |
| rateCodes com valor **diferente** | **0** |
| rateCodes do mapa que **não estão** na oferta indexada | **86** |
| famílias conferidas | 100 (53 com oferta confirmada · 47 sem eixo de região) |

Os 86 são **irredutíveis**: sondei uma lista larga de ofertas candidatas e nenhuma
os contém. Ou seja, **a calculadora publica rateCodes que o Bulk Price List não
publica** naquela região (todos do Redshift). Não é divergência de preço — é
ausência do outro lado. Isso é motivo para manter as duas fontes e **medir** a
cobertura, em vez de supor que as duas dizem a mesma coisa.

### 1.6 A correspondência família → oferta é DADO, não adivinhação

O mapa identifica a origem do preço por **família** (`lambda`, `rds-mysql-ondemand`,
`s3`); o Price List, por **offerCode** (`AWSLambda`, `AmazonRDS`, `AmazonS3`). Casar
os dois por semelhança de nome erra — e erra **em silêncio**:

| família | oferta real | o que a semelhança de nome sugeria |
|---|---|---|
| `datatransfer-calc` | `AWSDataTransfer` | nada: o nome não diz |
| `rds-mysql-ondemand` | `AmazonRDS` | `AmazonRDSForMySQL` — **não existe** |
| `queueservice` | `AWSQueueService` | `AmazonSQS` — **não existe** |
| `ebs-calculator` | `AmazonEC2` | `AmazonEBS` — **não existe** |
| `natgateway` | `AmazonEC2` | `AmazonVPC` — é recurso de VPC, mas o preço mora no EC2 |
| `s3` | `AmazonS3` | certo — mas a busca cortava candidatos nos 4 primeiros e o perdia |

O caso `s3` mostra o preço do erro: a heurística "maior interseção" elegeu
`AmazonS3` para a família `rds-aurora-storage` com 267 coincidências, quando o certo
era `AmazonRDS`. Na tela isso apareceu como **267 acertos e 337 ausências** — não
como falha. Ausência não grita.

Por isso a correspondência vive em `apps/calculadora/dados/correspondencia.json`,
com o caminho de obtenção registrado, e a conferência **indexa todas as ofertas do
serviço mais as companheiras** (`AWSDataTransfer`) — porque um mapa pode conter
dimensão publicada em outra oferta: o mapa do SQS e o do Kinesis Video trazem 155
rateCodes com a data de publicação do `AWSDataTransfer`.

### 1.4 Armadilhas já mapeadas por terceiros (não descobrir de novo)

Fonte: `aws-samples/sample-aws-pricing-calculator-mcp` (MIT-0, v1.3.1, 142★),
catálogo curado com 60 armadilhas auditadas. As que nos afetam:

- **US$ 0 silencioso:** salva sem erro e renderiza zero (Lambda precisa de
  memória, storage efêmero e arquitetura para dar preço).
- **A calculadora injeta campos sozinha** — `workload`, `workloadSelection`,
  `dataTransferForEC2`, `detailedMonitoringCheckbox` — mesmo sem marcá-los como
  obrigatórios.
- **`workload` É a quantidade de instâncias**, não um fator de utilização.
- **Transferência de dados** exige os 3 tipos (`INBOUND`, `OUTBOUND`,
  `INTRA_REGION`) presentes mesmo zerados; `OUTBOUND` exige `toRegion`
  (`External` para internet).
- **Termo omitido vira 3 anos** em contrato de desconto.
- **Reservada/Conversível somem com locação compartilhada** (remapeadas).
- A API da calculadora é **não documentada e pode mudar sem aviso** (palavras
  deles) — logo, tolerância a falha é requisito, não luxo.

### 1.5 O que outras implementações ensinam

| Projeto | O que aproveitar |
|---|---|
| `bytebase/dbcost` (85★, Go + Next.js) | arquitetura: **um cliente por provedor**, dado em **JSON versionado**, `seed` para o store, **cron no CI** para atualizar. Prova que o padrão "dado versionado + seed" escala |
| `ISU-HPC/aws-cost-calculator` (o que você mandou — idêntico ao fork, 1216 linhas) | **dimensionamento**: ordena por preço e escolhe a primeira instância que **cabe** nos recursos pedidos. E guarda `orig` **e** `latest`, permitindo reprocessar cálculo antigo com preço novo |
| `RafalWilinski/fargate-calc` (40★) | contraexemplo: preço **hardcoded** em `src/pricing.js`. É o "chapado" que não se repete |

---

## 2. Escopo

### 2.1 Serviços — os 24 da tabela (artigo do LinkedIn)

Mapa conferido contra o manifest. **Nem todo nome da tabela existe como um
serviço** — a coluna "realidade" é o que importa:

| # | Tabela | Realidade no catálogo |
|---|---|---|
| 1 | EC2 | `ec2Enhancement` (transform) + `catalog_ec2` local |
| 2 | EKS | `awsEks` ✅ |
| 3 | Lambda | `aWSLambda` |
| 4 | S3 | `amazonSimpleStorageServiceGroup` (pai) + filhos por classe |
| 5 | Elastic Block Store | `amazonElasticBlockStore` |
| 6 | Elastic File System | `amazonEFS` |
| 7 | VPC | `amazonVirtualPrivateCloud` (pai) + `awsPrivateLinkVpc`, `networkAddressTranslationNatGatewayVpc`, `transitGatewayVpc`, `dataTransferVpc` |
| 8 | Route 53 | `amazonRoute53` |
| 9 | Elastic Load Balancing | `elasticLoadBalancing` (pai) |
| 10 | Web Application Firewall | `awsWebApplicationFirewall` |
| 11 | RDS | **dividido por motor**: `amazonRDSForMySQL`, `amazonRDSForPostgreSQL`, `amazonRDSForSQLServer`, Aurora… |
| 12 | DynamoDB | `amazonDynamoDb` (pai) + filhos (on-demand, provisionado, DAX…) |
| 13 | Redshift | `amazonRedshift` |
| 14 | Elastic MapReduce | `amazonEMR` (pai) + nós master/core/task, Serverless, on EKS |
| 15 | Kinesis | **dividido**: `amazonKinesisDataStreams`, `amazonKinesisFirehose`, Video Streams, Managed Flink |
| 16 | SageMaker | `amazonSageMaker` (pai) + filhos |
| 17 | Glue | `awsGlue` (pai) + filhos |
| 18 | EventBridge | `amazonEventBridge` |
| 19 | SQS | `amazonSimpleQueueService` |
| 20 | SNS | `amazonSimpleNotificationService` (pai) |
| 21 | CloudWatch | `amazonCloudWatch` |
| 22 | CloudFormation | `awsCloudFormation` |
| 23 | IAM | ❌ **não está no catálogo** (verificado por 3 caminhos; só `awsIamAccessAnalyzer` existe) |
| 24 | KMS | `awsKeyManagementService` |

**Dependências que você citou:** `amazonCognito` ✅ e `amazonMacie` ✅ existem
como serviços autônomos. **SSO / IAM Identity Center não está no catálogo** — se
entrar na lista, entra como item de **custo zero declarado**, nunca como item sem
preço (a diferença é a mesma do "lacuna declarada" do coletor atual).

### 2.2 Não-objetivos

- Não cobrir os 440 serviços. O escopo é a tabela; o **motor** é que fica aberto.
- Não replicar o layout da AWS.
- Não usar a API de save da AWS para calcular por nós — o cálculo é nosso.

---

## 3. Decisões de arquitetura

| # | Decisão | Resolução |
|---|---|---|
| **D1** | Escopo de serviços | **Aberto no motor, fechado na entrega.** O catálogo é lido do manifest (440); a entrega prioriza os 24 da tabela. Serviço novo entra como **dado**, sem código |
| **D2** | Formulário de cada serviço | **Gerado a partir da definição.** Um renderizador lê `serviceDefinitionLocation` e desenha os campos. Não se escreve 24 formulários à mão |
| **D3** | Fonte de preço | **AWS Price List API** — a mesma da oficial, já provada idêntica por `rateCode` |
| **D4** | Onde o preço mora | **PostgreSQL** (ver §4). Banco e usuário próprios na instância compartilhada, conforme a regra de ouro da stack |
| **D5** | Atualização de preço | **Botão na tela**, à critério do usuário. Sem cron. (Difere do `dbcost` de propósito: o usuário vê o resultado da validação) |
| **D6** | Cálculo | **Local, nosso.** Cada número rastreável até o `rateCode` que o originou |
| **D7** | Verificação | **Conferência por `rateCode`** contra o mapa da oficial, como **teste automatizado** — não como revisão manual |
| **D8** | Categoria/agrupamento | ⚠️ **Não resolvido.** O manifest não tem categoria e ainda não achei a origem do agrupamento da tela. Fica em aberto até achar — não vai ser inventado |

---

## 4. Modelo de dados (PostgreSQL)

Banco `calculadora`, usuário `calculadora`, na instância compartilhada
(`postgresql.postgresql.svc.cluster.local:5432`). Schema `public`.

```sql
-- catálogo: o que existe (vem do manifest)
servico            (id, service_code UNIQUE, nome, descricao, sub_tipo,
                    is_active, definition_url, parent_service_code, visto_em)

-- formulário: os campos de cada serviço (vem da definição)
campo_servico      (id, service_code FK, campo_id, tipo, sub_tipo, rotulo,
                    opcoes JSONB, obrigatorio BOOL, ordem INT,
                    definition_version, visto_em)
                    UNIQUE (service_code, campo_id)

-- região
regiao             (id, codigo UNIQUE, rotulo, disponivel BOOL)

-- mapa de preços: a procedência de cada carga
mapa_preco         (id, familia, offer_code, publicacao_em, moeda,
                    url_origem, hash_conteudo UNIQUE, carregado_em, carregado_por)

-- preço unitário: a linha que a calculadora consome
preco              (id, mapa_preco_id FK, rate_code, sku, regiao_codigo,
                    preco NUMERIC(20,10), unidade, descricao, familia_produto,
                    atributos JSONB, vigente BOOL)
                    UNIQUE (rate_code, regiao_codigo) WHERE vigente

-- estimativa: o que o usuário monta
estimativa         (id, nome, descricao, regiao_codigo, criado_em)
grupo_estimativa   (id, estimativa_id FK, nome, pai_id NULL)   -- hierárquico
item_estimativa    (id, estimativa_id FK, grupo_id FK NULL,
                    service_code, entrada JSONB,      -- o que o usuário preencheu
                    calculado_em, total NUMERIC(20,10))
item_detalhe       (id, item_id FK, rate_code, quantidade NUMERIC, unidade,
                    preco_unitario NUMERIC(20,10), subtotal NUMERIC(20,10))
                    -- rastreabilidade: CADA linha de custo aponta o rate_code

-- histórico de carga (o que o botão fez, e o que recusou)
carga_log          (id, iniciado_em, concluido_em, resultado,
                    publicacoes JSONB, verificadas INT, divergentes INT,
                    ausentes INT, mensagem)
```

**`item_detalhe` é o coração do "não é fake news":** o total de um item é a soma
das suas linhas, e cada linha carrega o `rate_code` e o preço unitário usados. Se
um número parecer estranho, dá para abrir e ver de onde veio.

### 4.1 Correção depois de rodar: um rateCode pode estar em mais de um mapa

O plano supunha `1 rateCode = 1 linha`. A primeira carga de verdade mostrou que
não é bem assim: **`redshift` e `redshift-storage` publicam os MESMOS 140
rateCodes**, e o `cloudwatch` aparece no mapa do RDS e no do EC2. Medido: 16.402
entradas nos mapas viram **8.726 rateCodes únicos**.

O `UNIQUE (rate_code, regiao_codigo) WHERE vigente` continua certo — ele está
certo *porque* a dimensão é identificada pelo rateCode, e não pelo mapa. O que
mudou foi a carga: ela consolida antes de gravar, guarda em `atributos.mapas`
quem declara cada preço, e **recusa** se dois mapas discordarem do valor.

---

## 5. O botão de atualizar preço

Fluxo **em uma ação**, com portão de validação antes de tocar a base:

```
usuário clica "Atualizar preços"
        │
        ├─ 1. baixa o manifest e os mapas dos serviços do escopo
        │     (gzip tratado; host calculator.aws; tolerante a falha)
        │
        ├─ 2. VALIDA — e aqui é onde para:
        │     • toda publicação tem data legível?
        │     • o hash do conteúdo já foi carregado?  → nada a fazer, encerra "sem novidade"
        │     • cada rateCode do escopo resolve no Price List?
        │     • algum preço mudou > X% desde a carga anterior?  → marca para revisão
        │     • alguma dimensão que JÁ usamos desapareceu?      → ERRO
        │     • a conferência contra o mapa oficial bate?       → divergência = ERRO
        │
        ├─ 3. SE HOUVER INCONSISTÊNCIA → NÃO grava. Mostra o relatório:
        │     quantos verificados, quantos divergentes, quais rateCodes.
        │     A base fica intacta e a calculadora continua com o preço anterior,
        │     que era íntegro.
        │
        └─ 4. SE ESTIVER ÍNTEGRO → grava numa transação:
              novo mapa_preco, preços marcados vigentes, anteriores viram
              histórico (nunca DELETE), e o carga_log registra a operação.
```

Regras que ficam valendo:

- **Nunca apagar preço.** Preço antigo vira histórico — é o que permite responder
  "por que o mês passado deu outro número" (a lição `orig`/`latest` do ISU-HPC).
- **Nada é gravado parcialmente:** validação e gravação são separadas, e a
  gravação é uma transação.
- **O mesmo botão tem modo `dry-run`**, para o teste automatizado usar sem gravar.

---

## 6. Camadas da aplicação

```
web (SPA)            escolhe serviço · preenche · vê por serviço/grupo/total
   │  HTTP
api (stdlib)         /catalogo /servicos/{code}/campos /regioes /precos
                     /estimativas /calcular /atualizar-precos (+ dry-run)
   │
   ├─ definição      lê a definição do serviço e devolve o formulário
   ├─ cálculo        entrada + preço vigente → linhas com rate_code
   ├─ coleta         manifest + mapas da oficial (gzip, cache, tolerância)
   └─ store          PostgreSQL (o esquema de §4)
```

Mantém o que já funciona hoje (`api/servidor.py` é stdlib, `api/precos.py` tem os
fatores de unidade e as regras de quantidade) e **acrescenta** as camadas de
catálogo, definição e persistência. O `buscar_precos.py` atual vira o
**coletor do Price List** — é ele que extrai os preços oficiais, e ele já provou
que sabe fazer isso (`problemas: []`, 10 itens, 1.249 modelos).

---

## 7. Fases de implementação

Cada fase é verificável sozinha e não depende da seguinte.

| Fase | Entrega | Como se verifica |
|---|---|---|
| **F1** | Coletor do mapa oficial + **conferência `rateCode`** para os 24 | ✅ **feito**: 10.150 iguais · 0 diferentes · 86 ausentes irredutíveis (Redshift) · correspondência em `dados/correspondencia.json` |
| **F2** | Schema no Postgres + carga dos preços + `carga_log` | ✅ **feito e executado** (2026-09-20): **8.726 rateCodes vigentes** em us-east-1, 0 divergências, 125 testes. `api/pg.py` (cliente em biblioteca padrão, SCRAM-SHA-256), `sql/001-schema.sql`, `carregar_precos.py` com portão, Job declarativo em `infrastructure/postgresql/init-job.yaml` — ver [02-f2-carga.md](02-f2-carga.md) |
| **F3** | Leitor de definição → `/servicos/{code}/campos` | o formulário do Lambda tem os campos da definição, com tipo e opções |
| **F4** | Cálculo de **um** serviço ponta a ponta (KMS: 6 dimensões) | total nosso == total da oficial para o mesmo config |
| **F5** | Botão de atualizar preços com o portão de validação | carga boa grava; carga com divergência **recusa e não grava** |
| **F6** | Cálculo dos serviços por família (compute, storage, rede, dados) | um por família, conferido contra a oficial |
| **F7** | Grupos hierárquicos + totais | por serviço, por grupo e total |
| **F8** | O laboratório vira **preset** (a vitrine atual) | o número do `docs/aws/README.md` continua reproduzível |

---

## 8. Riscos e o que ainda não sei

| Risco | Estado |
|---|---|
| **A fórmula** — tenho as dimensões e os preços; **não tenho a aritmética** que os combina (ela vive no bundle do app, não na definição) | 🔴 aberto. Cada serviço terá a fórmula **nossa**, documentada e testada contra a oficial |
| **A origem do agrupamento por categoria** | 🔴 aberto. Não está no manifest |
| API da oficial **não documentada** | 🟡 aceito: cache + tolerância a falha + preço antigo íntegro |
| **Regiões divergentes** | 🟢 medido e aceito: a cobertura é **por mapa** (23 a 110 regiões), não um número único. Onde a AWS não publica o serviço, ele não aparece — e isso é coberto com honestidade em vez de inventado |
| Preço que muda entre o cálculo e a leitura | 🟢 mitigado: cada item guarda o `rate_code` e o preço usado no momento |
| US$ 0 silencioso | 🟢 mitigado: item sem preço é **lacuna declarada**, nunca zero |

---

## 9. Critério de pronto

- [ ] Os 24 serviços da tabela calculando, com config por serviço e região
- [ ] Cada linha de custo rastreável até o `rate_code` que a originou
- [ ] Botão de atualizar preço que **recusa** carga inconsistente
- [ ] Conferência `rateCode` batendo contra o mapa oficial, como teste
- [ ] Nenhum número sem procedência: sem preço → lacuna, não zero
- [ ] O preset do laboratório reproduzindo o mesmo número de hoje

---

## 10. Fontes

- AWS Pricing Calculator — guia do usuário (índice completo):
  `docs.aws.amazon.com/pricing-calculator/latest/userguide/` (lido 2026-09-20)
- Manifest do catálogo: `d1qsjq9pzbk1k6.cloudfront.net/manifest/en_US.json`
  (HTTP 200, 398 KB, 440 serviços — 2026-09-20)
- Mapas de preço da oficial:
  `calculator.aws/pricing/2.0/meteredUnitMaps/<família>/USD/current/<família>.json`
  (Lambda 2026-09-19 · EKS 2026-09-18 · KMS e Route 53 2026-09-11)
- AWS Bulk Price List: `pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<offer>/current/region_index.json`
  (271 ofertas no índice — 2026-09-20)
- `aws-samples/sample-aws-pricing-calculator-mcp` v1.3.1 (MIT-0):
  catálogo curado, armadilhas e a documentação dos caminhos internos
- `bytebase/dbcost` (85★) — arquitetura de referência
- `ISU-HPC/aws-cost-calculator` — dimensionamento e histórico de preço
- Tabela comparativa AWS · Azure · GCP · Oracle Cloud — artigo do autor
  (2026), que define o escopo dos 24 serviços
- Código atual: `apps/calculadora/` (coletor, núcleo de cálculo, API, SPA, 90 testes)
