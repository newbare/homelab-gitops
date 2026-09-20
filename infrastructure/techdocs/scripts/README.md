# Scripts do TechDocs

Scripts de bancada — ferramentas para **reproduzir e conferir** o caminho de
geração e publicação do site. Nada aqui é pré-requisito de produção: produção é
o CronJob `techdocs-builder`, declarado em `../templates/cronjob.yaml`.

| Script | Para quê |
|---|---|
| `publish_site.py` | publica um site **já gerado** no bucket (com `--dry-run` para só conferir) |

---

## `publish_site.py`

### Por que existe, se o cron já publica

Porque **ferramenta de bancada também precisa ser declarada**. Um comando
digitado no terminal não fica: não está no repositório, não tem `--help`, e na
próxima vez alguém reinventa — ou erra o caminho no bucket, ou esquece o
`--endpoint-url`, ou sobe sem apagar o que ficou órfão.

O script é o mesmo passo do cron, mas com as decisões escritas em código: qual
endpoint, qual prefixo, o que conta como "arquivo que mudou" e o que fazer com o
que sumiu do site.

### Preparação (uma vez)

```bash
python3 -m venv infrastructure/techdocs/scripts/.venv
infrastructure/techdocs/scripts/.venv/bin/pip install \
  -r infrastructure/techdocs/scripts/requirements.txt
```

O `.venv/` é ignorado pelo Git (ver `.gitignore` ao lado) — mesmo padrão de
`infrastructure/keycloak/scripts/`.

### Conferir sem publicar

```bash
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test

infrastructure/techdocs/scripts/.venv/bin/python \
  infrastructure/techdocs/scripts/publish_site.py \
  --site-dir /tmp/tfdocs-site --dry-run
```

Saída real de uma execução (2026-09-19):

```
endpoint : http://192.168.99.5:4566
bucket   : resilience-techdocs
prefixo  : default/component/documentacao-resilience/
arquivos : 74 locais

remotos  : 74 objetos sob o prefixo

  enviar   .../00-visao-geral/index.html  (conteúdo diferente)
  apagar   .../assets/javascripts/bundle.79ae519e.min.js  (não existe mais no site)

enviados : 21
idênticos: 53
apagados : 4

(--dry-run: nada foi alterado)
```

### ⚠️ Gere o site com a MESMA imagem do cron

O build canônico é o do CronJob: `spotify/techdocs:1.2.9`. Se você gerar com
outra versão de mkdocs/techdocs-core, o site sai diferente — **inclusive os
nomes dos assets, que carregam hash de conteúdo** — e aí o script publica uma
versão enquanto o cron publica outra a cada 30 minutos. Ping-pong.

Foi exatamente o que a execução acima mostrou: build local com
`techdocs-core 1.7.1` contra o do cron com a imagem `1.2.9` → 21 arquivos
diferentes e 4 assets órfãos.

### Argumentos

| Argumento | Padrão | Para quê |
|---|---|---|
| `--site-dir` | *(obrigatório)* | diretório do site gerado (precisa ter `index.html` na raiz) |
| `--bucket` | `resilience-techdocs` | bucket de destino |
| `--entity` | `default/component/documentacao-resilience` | entity triplet; é o prefixo no bucket |
| `--endpoint` | `$FLOCI_ENDPOINT` ou `http://192.168.99.5:4566` | endpoint S3 (Floci é S3-compatível) |
| `--region` | `us-east-1` | exigido pelo SDK, mesmo no emulador |
| `--force` | — | reenvia tudo, sem comparar MD5 |
| `--keep-stale` | — | não apaga do bucket o que sumiu do site |
| `--dry-run` | — | mostra o plano e não altera nada |

As **credenciais nunca vêm de flag**: só do ambiente (`AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`). Sem elas o script aborta explicando o que exportar.
