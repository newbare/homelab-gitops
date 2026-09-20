# Payload de teste — NÃO REUSAR

Estes dois arquivos foram publicados uma vez no bucket para provar que o backend
TechDocs lê de lá (Incremento 1). Estão preservados pelo que **ensinam**, não
para serem usados.

O `index.html` foi **escrito à mão**, sem `mkdocs`. Ele aparece no reader, mas a
tela fica num **spinner eterno** — o leitor espera o tema do mkdocs (container
`md-container`), que este arquivo não tem.

> **Nunca valide o reader com HTML escrito à mão.** Para testar renderização,
> gere o site com `mkdocs` de verdade.

A história completa, o comando exato que publicou isto e a lição estão em
`../README.md`. O que roda em produção é o CronJob `techdocs-builder`.
