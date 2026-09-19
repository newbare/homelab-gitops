# Fase 2 do Backstage — Plano: TechDocs

> **Fase:** 2 de 3 (Pesquisa → **Plano** → Implementação)
> **Pesquisa base:** [`12-pesquisa-catalogo.md`](./12-pesquisa-catalogo.md) §6.5
> **Status:** proposta. Nada aplicado.

---

## 1. Objetivo

Fazer a documentação do repositório aparecer na Backstage, na aba **Documentação**
de cada entidade — o "documentos de projeto" do modelo que você descreveu.

**Não-objetivos:** escrever documentação nova; migrar as docs atuais; mexer em
catálogo (F1 está fechada).

---

## 2. O bloqueio — verificado no Pod, não na doc

A pesquisa (§6.5) mostrou que a doc trata `runIn: docker` como configuração de
desenvolvimento. **O Pod confirma que é pior que isso:**

| Verificação dentro do Pod | Resultado |
|---|---|
| `which mkdocs` | **não existe** |
| `which python3` / `pip3` | **não existe** |
| `which docker` | *"(sem docker)"* |
| `/var/run/docker.sock` | **inexistente** |
| `mkdocs.yml` no repositório | **nenhum** |

**Consequência:** hoje o TechDocs não pode gerar documentação de forma alguma.

- `runIn: docker` → impossível: não há binário nem socket.
- `runIn: local` → impossível: não há mkdocs nem Python.

Isso não é bug — a imagem `newbare/homelab-backstage:v27` é o backend Node puro.
A config aponta para um gerador que nunca existiu no container.

---

## 3. Opções, com custo

| | Caminho | O que exige | Veredito |
|---|---|---|---|
| **A** | Customizar a imagem: instalar Python + mkdocs + techdocs-core, usar `runIn: local` | Alterar o `Dockerfile`, **rebuild** e nova tag; ~+200 MB de imagem | Funciona, mas coloca toolchain Python dentro de um serviço Node |
| **B** | `builder: external` + gerador fora do Pod + publisher em storage | Job de geração **e** storage durável | **Recomendado** — é o setup que a própria doc chama de *"Recommended"* |
| **C** | Montar o socket do Docker no Pod | Acesso ao daemon do nó | ❌ **Descartado.** O Pod passaria a poder criar containers como root |

### Por que B, e não A

A geração de MkDocs é um passo de **build**, não de execução. Fazer o backend
Node gerar docs a cada abertura de página mistura responsabilidades e mantém a
toolchain Python carregada em memória permanentemente.

Com `builder: external`, o Pod só **lê e serve** arquivos estáticos — e aí ele não
precisa nem de Python nem de Docker. É a separação que a doc recomenda.

### O publisher: aqui está o detalhe que decide

`publisher.type: local` **não serve**: a doc diz que ele cria um diretório
`static` na raiz do backend — que em Kubernetes é **efêmero**. Como o Pod é
recriado a cada mudança de config (e travou no `ImagePullBackOff` três vezes
hoje), as docs seriam perdidas a cada restart.

**O publisher certo é `awsS3` — apontando para o Floci.** A doc descreve
`s3ForcePathStyle` como a opção que *"allows providers like **LocalStack**, Minio
and Wasabi to be used to host tech docs"*. O Floci é drop-in do LocalStack, e o
serviço `s3` está `running`.

### Por que a geração não pode ser no GitHub Actions

Seria o caminho óbvio, mas **o Floci está na LAN (192.168.99.5)**, e um runner do
GitHub não alcança a rede local. Publicar do CI externo para o Floci exigiria
expor o Floci à internet — o que anula a razão de existir um emulador local.

**Logo: o job de geração roda dentro do cluster**, usando a imagem `spotify/techdocs`,
com saída para o S3 do Floci.

---

## 4. O padrão quando não há projeto de código — e você estava certo

Levantado na doc oficial depois de você perguntar. São **dois mecanismos**, e o
segundo muda o desenho.

### 4.1 Documentação avulsa — `spec.type: documentation`

Fonte: [TechDocs — Creating and publishing](https://backstage.io/docs/features/techdocs/creating-and-publishing)

> *"There could be some situations where you don't want to keep your docs close to
> your code, but still want to publish documentation... For this case, you can
> create a **documentation component**, which will be published as a **standalone**
> part of TechDocs."*

É um `Component` normal com `spec.type: documentation`. **Não exige projeto de
código.** A intuição estava correta.

### 4.2 Um dono, muitos referenciadores — `backstage.io/techdocs-entity`

Fonte: [Well-known Annotations](https://backstage.io/docs/features/software-catalog/well-known-annotations)

> *"The value of this annotation informs of an **external entity that owns the
> TechDocs**. This allows you to **reference TechDocs from a single source without
> either duplicating the TechDocs in the TechDocs page or needing multiple builds of
> the same docs**."*
>
> *"This is for situations where you have **complex systems where they share a
> single repo, and likely a single TechDoc location**."*

**Este é exatamente o nosso caso:** 12 Components, **um** repositório, **uma**
pasta `docs/`. Sem esta anotação, o Backstage tentaria construir o mesmo site
doze vezes.

Anotações relacionadas:

| Anotação | Papel |
|---|---|
| `backstage.io/techdocs-ref` | Onde o conteúdo está. `dir:.` (relativo ao `catalog-info.yaml`) ou `url:<url>` (absoluto) |
| `backstage.io/techdocs-entity` | Qual entidade **dona** do TechDocs — o referenciador **não** precisa de `techdocs-ref` |
| `backstage.io/techdocs-entity-path` | Deep link para uma subpasta dentro das docs de outro dono |

### 4.3 Sintaxe da `techdocs-ref` — a doc prevê o seu caso

> *"**In unusual situations where the documentation for a catalog entity does not
> live alongside the entity's source code**, the value of this annotation can point
> to an absolute URL... for example: `url:https://github.com/backstage/backstage/tree/master`"*

Ou seja: docs separadas do código **não** é gambiarra — é caso previsto e nomeado.

### 4.4 Desenho que sai disso

```
Component  documentacao-resilience      (spec.type: documentation)
  └─ backstage.io/techdocs-ref: dir:.
     \u2500 mkdocs.yml na raiz do repo
     \u2500 docs/  \u2190 o acervo inteiro (jornadas, runbooks, auditoria)

Componentes argocd, backstage, keycloak, istio, kiali, prometheus, jaeger,
metalib, cert-manager, trust-manager, metrics-server, bookinfo
  \u2514─ backstage.io/techdocs-entity: component:default/documentacao-resilience
```

**Um único site construído. Doze entidades apontando para ele.** É o que a doc
chama de evitar *"multiple builds of the same docs"*.

### 4.5 O que já temos para publicar

O repositório **já tem** acervo substancial em `docs/`: as jornadas por fase,
runbooks, troubleshooting, pesquisa e plano do catálogo, as três decisões da
auditoria. É esse material que vale publicar — e ele é a razão de o TechDocs
fazer sentido aqui.

---

## 5. Incrementos propostos

**Incremento 1 — provar que o Pod consegue ler.**
✅ **Bucket: FEITO (2026-09-19)** — `resilience-techdocs`, criado pelo stack
`terraform/iam-users`: versionamento `Enabled`, SSE `AES256`, transição para
`ONEZONE_IA` em 30 dias, sem expiração de objeto. Decisões, armadilhas e fontes:
[`terraform/iam-users/README.md`](../../terraform/iam-users/README.md).

Falta: publicar um `index.md` de teste, mudar `techdocs.publisher.type` para
`awsS3` com o endpoint do Floci e verificar que a aba de documentação abre lendo
do S3. *Sem isso, nada mais importa: se o Pod não lê, gerar é inútil.*

**Incremento 2 — gerar de verdade.**
Job/CronJob in-cluster com a imagem `spotify/techdocs`, que clona o repositório,
roda `mkdocs build` e publica no bucket. Junto: o `mkdocs.yml` que ainda não
existe.

**Incremento 3 — ligar na entidade.**
`catalog-info.yaml` do `Component` de documentação com
`backstage.io/techdocs-ref: dir:.`, e a nav do `mkdocs.yml` cobrindo as jornadas.

---

## 6. Decisões que dependem de você

| # | Decisão | Opções |
|---|---|---|
| **T1** | Caminho de geração | (a) imagem custom com Python+mkdocs · (b) `builder: external` + Job in-cluster |
| **T2** | Publisher | (a) `local` (efêmero — perde no restart) · (b) `awsS3` no Floci |
| **T3** | Escopo do que publicar | (a) só `docs/backstage/` · (b) o `docs/` inteiro |
| **T4** | Bucket | ✅ **RESOLVIDO (2026-09-19)**: `resilience-techdocs` — versionamento `Enabled`, SSE `AES256`, transição 30d → `ONEZONE_IA`, **sem expiração** de objeto |
| **T5** | Um dono ou um por componente | (a) **um** `Component type: documentation` + 12 referências via `techdocs-entity` · (b) TechDocs em cada Component |

**Recomendação:** T1 = (b), T2 = (b), T3 = (b), **T5 = (a)**.

**Sobre T5:** a opção (a) é a que a doc descreve para *"complex systems where they
share a single repo, and likely a single TechDoc location"* — e evita 12 builds do
mesmo site. A opção (b) só faria sentido se cada componente tivesse documentação
própria, o que não é o caso.

---

## 7. Riscos conhecidos

| Risco | Mitigação |
|---|---|
| O Pod não alcançar o Floci (rede) | O Pod alcança o Keycloak via `hostAliases`; o Floci está em outra máquina, então é preciso verificar rota e DNS antes de assumir |
| `awsS3` sem `s3ForcePathStyle` falha | A doc é explícita sobre a necessidade dessa opção para emuladores |
| Credenciais do S3 | O Floci aceita chaves descartáveis; não usar credencial real |
| Rebuild de imagem (se T1 = a) | Traz o `ImagePullBackOff` de volta; mais um motivo para preferir (b) |

---

## 8. Existe alternativa mais barata

TechDocs é o item mais caro dos que restam. Se o objetivo é valor rápido, a
**ordem alternativa** seria:

1. **Autorização** (§9.1 do plano do catálogo) — o seu requisito de "só admins
   veem infra". Exige `permission.enabled=true` e uma policy própria; também é
   mudança de código + imagem.
2. **Template do scaffolder (F4)** — praticamente só YAML. O motor já funciona
   (a página *Criar* existe). É o item que você descreveu com mais detalhe.

Nenhuma das duas é mais simples que a outra em absoluto — mas o template não
depende de infraestrutura nova (nem bucket, nem job, nem rede), e o TechDocs
depende de três coisas que ainda não temos.
