# Documentação do laboratório

Acervo do laboratório de estudos em GitOps, DevSecOps e infraestrutura: o que foi
feito, por que foi feito assim, o que quebrou no caminho e como consertar.

Este site **não é escrito à mão**: ele é *gerado* a partir da pasta `docs/` deste
repositório, pelo `mkdocs` com o plugin `techdocs-core`, e publicado no bucket
`resilience-techdocs` — de onde o Backstage o lê. Ou seja: editar o markdown e
republicar é o único passo necessário para atualizar o que você está lendo.

## Por onde começar

| Se você quer... | Vá para |
|---|---|
| entender o objetivo, a stack e as fases | [Visão geral](00-visao-geral.md) |
| saber como o Backstage foi montado e por quê | [Backstage — contexto](backstage/00-contexto.md) |
| subir/derrubar ou diagnosticar algo agora | [Runbook](backstage/04-runbook.md) |
| resolver um problema que apareceu | [Troubleshooting](backstage/05-troubleshooting.md) |
| ver como o catálogo foi modelado | [Pesquisa do catálogo](backstage/12-pesquisa-catalogo.md) |
| ver o plano do TechDocs (este site) | [Plano do TechDocs](backstage/14-plano-techdocs.md) |

## Seções do acervo

- **`backstage/`** — a jornada do portal do desenvolvedor: contexto, arquitetura,
  decisões, runbook, troubleshooting, referências e o diário de cada fase.
- **`certificados/`** — a CA interna, como gerar, instalar e confiar: o problema
  do TLS que persegue qualquer laboratório com domínio próprio.
- **`auditoria/`** — a avaliação de maturidade da plataforma, com o prompt usado,
  os critérios e o relatório.
- **`praticas/`** — as práticas de Git e de CLI adotadas no repositório.

## Uma nota de honestidade

Este acervo registra **erros**, não só acertos. Vários documentos descrevem
caminhos que foram tentados e abandonados, com o motivo — porque um laboratório
que só documenta o que deu certo ensina metade do que deveria.
