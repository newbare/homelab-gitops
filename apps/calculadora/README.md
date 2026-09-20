# Calculadora Resilience — custo do laboratório em AWS

> Quanto custa rodar **este laboratório** na AWS, por uma semana de implantação —
> com preço vindo da lista oficial da AWS, não de memória.

No cluster: **https://calculadora.local** · contrato da API: **`/api/docs`**

```console
$ python3 calcular.py

  Laboratório Resilience Cloud — single node em AWS
  Região: us-east-1 (US East (N. Virginia))   Janela: 168 h

  TOTAL em 168 h .............. US$ 50,2281
  por hora .................... US$ 0,2990
  por dia ..................... US$ 7,1754
  projeção 730 h (1 mês) ...... US$ 209,8900

  Por grupo (na janela):
    computacao       US$    32,2560    64.2%
    armazenamento    US$    12,1466    24.2%
    operacao         US$     3,1856     6.3%
    rede             US$     2,6400     5.3%
```

---

## O que a calculadora responde, e o que ela se recusa a responder

Responde: **quanto custa esta topologia**, linha por linha, com a data em que o
preço foi lido.

Não responde — e isto é escolha, não limitação:

| Pergunta | Por que não |
|---|---|
| "E se eu reservar 1 ano?" | Reserva e Savings Plan exigem **compromisso** de 1 a 3 anos. Numa janela de 7 dias eles não se aplicam, e mostrar número de reserva aqui seria propaganda, não custo. |
| "E a região de São Paulo?" | O catálogo e os preços valem para a região **coletada**. O seletor lista as 106 regiões (dado real da AWS) e diz qual tem preço — oferecer as outras para cálculo seria inventar número. |
| "E com alta disponibilidade?" | Esta é uma topologia **single node**, declarada como tal nas premissas. HA é outra topologia, com outro BOM. |

---

## As três decisões que definem este app

### 1. Nenhum preço mora no código — nem no BOM, nem na API

Os preços vêm de `dados/prices.json`, um **snapshot da lista oficial da AWS**
que carrega a `publicationDate` que a própria AWS publica. O documento e o
painel citam a data porque ela veio de dentro do dado.

E isso não é preciosismo: um preço digitado à mão envelhece sem avisar. Um preço
com procedência **diz quando foi lido**.

### 2. Nenhum catálogo mora no código

Regiões, serviços e modelos de máquina são **descobertos** da fonte:

| Seletor | De onde vem | Na coleta de referência |
|---|---|---|
| Região | `region_index.json` do serviço | **106** regiões |
| Serviço | índice raiz da lista oficial | **271** serviços |
| Modelo de EC2 | catálogo do arquivo da região | **1.249** modelos com preço, vCPU e memória |

A primeira versão disto fixava `us-east-1` e `m6i.xlarge` no código. Estava
errado: uma SPA que só conhece uma região não mostra o que a AWS oferece, mostra
o que o autor digitou.

### 3. Biblioteca padrão, e por isso nenhuma imagem para construir

Sem Flask, sem FastAPI, sem `pip install` no Pod. O container é a imagem
**oficial** `python:3.13-alpine` e o app roda de dentro de **ConfigMaps** — o
código, o HTML, o CSS, os logos e os dados são arquivos de texto no Git.

```
web/*  ─┐
api/*  ─┼─→ ConfigMap ─→ /app/{web,api,dados} ─→ python3 api/servidor.py
dados/*─┘
```

O que se ganha: não existe imagem própria para construir, registry para manter,
tag para esquecer de subir, nem `latest` para envelhecer. **`git push` é o
deploy.**

O que se perde, e está declarado: nada de concorrência de verdade sob carga,
TLS próprio, autenticação ou métricas. É um painel interno de leitura servindo
arquivo local — é o que cabe.

---

## Os arquivos

```
buscar_precos.py        coleta RARA e PESADA da lista oficial (EC2 = 288 MB)
carregar_precos.py      carrega os mapas OFICIAIS no PostgreSQL (fase F2)
calcular.py             CLI — imprime a mesma conta que o painel faz
api/
  precos.py             o núcleo: fator de unidade, cálculo, projeção mensal
  servidor.py           serviço HTTP (biblioteca padrão) + rotas de descoberta
  pg.py                 cliente PostgreSQL em biblioteca padrão (SCRAM-SHA-256)
  oficial.py            cliente das fontes oficiais (manifest, definição, mapas)
  openapi.json          a especificação 3.1, escrita à mão (artefato de desenho)
sql/
  000-banco.sql         banco e usuário (exige superusuário, via psql)
  001-schema.sql        o modelo de preço e estimativa (idempotente)
dados/
  bom.json              o que compõe a infra + o PORQUÊ de cada linha
  prices.json           snapshot oficial, com procedência e data
  escopo.json           os 24 serviços do escopo, com as raízes verificadas
  correspondencia.json  família do mapa -> oferta do Price List (confirmada)
web/
  index.html/app.js     a SPA (JavaScript puro, sem React, sem build)
  docs.html             a tela que renderiza a spec OpenAPI
  styles.css            identidade visual — tokens do tema do Backstage
  tec-*.svg             logos da stack (uma vez baixados, versionados aqui)
tests/                  aritmética, contrato do dado, borda HTTP, protocolo e portão
```

---

## Uso

```bash
make                    # mostra os alvos
make teste              # a suíte inteira
make tabela             # o número de 7 dias no terminal
make servir             # painel local em http://localhost:8080
make snapshot           # RECOLETA da lista oficial (EC2: 288 MB, leva minutos)
```

E os alvos da fase F2 (os preços no PostgreSQL — o motor agnóstico):

```bash
make f2                 # TUDO: banco, schema, carga e conferência
make carga-seca         # coleta e confere SEM gravar nada
make carga-conferir     # o que está na base
```

O passo a passo desta fase, e as decisões que a carga toma, estão em
[`docs/calculadora/02-f2-carga.md`](../../docs/calculadora/02-f2-carga.md).

### Por que o snapshot é um passo separado

Porque o arquivo do EC2 em uma região tem **288,8 MB** (medido: o JSON tem
459 MB, e o servidor da AWS não oferece gzip). Isso não cabe em requisição, e
não faz sentido baixar a cada leitura.

O desenho separa o passo **caro e raro** do **barato e frequente**:

```
buscar_precos.py  ──▶  dados/prices.json  ──▶  a API e o painel (instantâneos)
   (minutos, no host        (versionado no Git,
    de operação)             com data e fonte)
```

E o refresh roda no **host de operação**, que é onde o Terraform e o Python com
venv vivem — não na máquina de quem está olhando o painel.

### O `--dump` não é enfeite

`buscar_precos.py --dump arquivo.json` grava os candidatos crus de cada
consulta. Existe porque o arquivo tem dezenas de colunas e os nomes variam entre
famílias de produto: quando um filtro casa zero **ou casa demais**, o dump mostra
o que o arquivo realmente contém. Foi assim que se descobriu que o IPv4 público
não está no arquivo do EC2 (a cobrança mora no offer do VPC) e que a
"transferência de dados" daquele arquivo é só inter-região.

---

## Duas armadilhas que custaram passadas de 288 MB

### Desempatar por preço é como o painel passa a mentir

A primeira versão, quando mais de uma linha casava, escolhia **a mais barata**.
Errou três vezes seguidas:

1. egress no arquivo do EC2 → pegou US$ 0,02/GB (inter-região) no lugar da saída
   para internet, que nem está naquele arquivo;
2. egress no `AWSDataTransfer` → pegou **US$ 0,00/GB** de uma variante `Global-*`,
   porque o filtro por substring também casava com ela;
3. e os escalões: `min` escolhe sempre a **faixa mais barata**, nunca o preço de
   tabela.

Hoje a regra é o contrário: **casando mais de um, o item NÃO é escolhido**. Ele
vira problema declarado, e a linha aparece como lacuna. Preço **ausente** é
visível e alguém corrige; preço **errado** não chama ninguém.

### `"quantidade": "janela"`

As horas do BOM (168) são a **janela**, não a duração do servidor. Sem distinguir
as duas coisas, a projeção de um mês mantinha as 168 h e a maior linha do custo
saía **~4x mais barata** — um número errado com cara de certo.

Linhas que ficam ligadas o tempo todo declaram `"quantidade": "janela"`, e a
quantidade delas passa a ser a janela pedida. Foi o primeiro bug que os testes
pegaram, e ele não aparecia em nenhuma leitura de código: só na conta de 730 h.

---

## Testes

```console
$ make teste
87 passed in 1.08s
```

Três famílias, e a separação é de propósito:

| Arquivo | O que protege |
|---|---|
| `test_precos.py` | **aritmética**, com snapshot sintético de números redondos. Não depende do mercado da AWS: um teste de conta que quebra porque o `m6i.xlarge` subiu não é teste de conta. |
| `test_snapshot.py` | **contrato do dado**: procedência em cada serviço, ausência de problemas, preços conhecidos, e a deriva entre o BOM e o snapshot (todo `preco_ref` existe, todo modelo padrão está no catálogo). |
| `test_servidor.py` | **borda HTTP**: mapa de códigos (400 x 404 x 403 x 405), confinamento de caminho, extensões servidas, e a coerência nos dois sentidos entre a spec OpenAPI e as rotas que existem. |

Na primeira execução a suíte reprovou **três bugs reais**, e vale registrar
porque é o argumento a favor de escrever teste antes de decorar tela: a projeção
mensal 4x barata, um `AttributeError` que derrubava qualquer `POST`, e o logo que
não era servido localmente (no cluster ele chega pelo `binaryData` do ConfigMap,
e o servidor de dev não sabia disso).

---

## Publicação

Declarada em `infrastructure/calculadora/app.yaml` (Application do ArgoCD, wave
9), com o namespace em `infrastructure/namespaces/calculadora.yaml`. O chart é
**este diretório** — `apps/calculadora/` tem `Chart.yaml`, `values.yaml` e
`templates/`, e os arquivos do app entram nos ConfigMaps via `.Files.Glob`.

Uma consequência de estar aqui dentro: os assets de marca (`assets/*.png`) são
**cópia** dos do Backstage. O Pod não alcança o repositório, então a marca viaja
junto com o app. É duplicação consciente e registrada, não descuido.
