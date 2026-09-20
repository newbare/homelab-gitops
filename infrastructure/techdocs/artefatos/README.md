# Artefatos de teste

Artefatos usados para **provar um caminho** e guardados aqui pelo que eles
ensinam — não porque devam ser reusados. O site de verdade é gerado pelo CronJob
`techdocs-builder` (ver `../templates/cronjob.yaml`).

| Diretório | O que provou | Veredito |
|---|---|---|
| `payload-de-teste/` | que o backend TechDocs **lê** do bucket no Floci | cumpriu o papel e foi descartado |

---

## `payload-de-teste/` — a prova de leitura do Incremento 1

### O que era

Um site TechDocs escrito **à mão**: um `index.html` de seis linhas e um
`techdocs_metadata.json`. Não veio de `mkdocs build`. Foi publicado no bucket
`resilience-techdocs`, sob o prefixo da entity, com CLI:

```bash
aws s3 cp index.html \
  s3://resilience-techdocs/default/component/documentacao-resilience/index.html \
  --endpoint-url http://192.168.99.5:4566
```

O objetivo era estreito e legítimo: **isolar a variável**. Antes de culpar o
builder, o mkdocs ou a imagem, dava para responder uma pergunta só — "o backend
TechDocs, com `builder: external`, consegue ler o que está no bucket e servir?"
A resposta foi sim.

### A lição que ficou

A página abriu. O **conteúdo apareceu**. E mesmo assim a tela mostrava um
**spinner eterno**.

O motivo: o TechDocs Reader não serve HTML solto — ele espera a estrutura e as
classes do **tema do mkdocs** (o container `md-container`, entre outras). Sem
tema, o JavaScript do reader fica girando esperando algo que nunca chega.

Conclusão, escrita aqui para não ser reesquecida:

> **Nunca valide o reader com HTML escrito à mão.** Se o objetivo é testar a
> renderização, gere um site com `mkdocs` de verdade — é a única forma de o
> teste dizer alguma coisa sobre a experiência real.

### O que substituiu isto

O Incremento 2 — o CronJob que clona o repositório, roda
`mkdocs build` com a imagem oficial e sincroniza o resultado para o mesmo
prefixo. O build é o mesmo, então a comparação é honesta.

### Por que o publish não ficou sendo CLI

Publicar com `aws s3 cp` / `aws s3 sync` digitado na mão funciona uma vez e
**não deixa rastro**: o comando morre no histórico do shell. Não tem `--help`,
não tem revisão, e o próximo a precisar disso vai reinventar — provavelmente
esquecendo o `--endpoint-url` ou deixando objeto órfão no bucket.

O caminho agora está em `../scripts/publish_site.py`, com as decisões escritas:
endpoint, prefixo, o que conta como "mudou" (MD5 contra `ETag`, não tamanho) e o
que fazer com o que sumiu do site. Tem `--dry-run` justamente para poder
conferir sem publicar.
