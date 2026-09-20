# AWS — pré-requisitos e marco zero

> O que precisa **existir e estar configurado antes** de mexer na AWS neste
> repositório. O que dá para declarar está em Terraform. O que não dá está aqui,
> com o comando e com o motivo de não dar.

**Calculadora do custo:** https://calculadora.local · **contrato da API:** `/api/docs`

---

## 1. Os dois ambientes

Este laboratório roda em dois lugares, e eles **não** são o mesmo ambiente com
endereço diferente. Mudam credencial, topologia e o significado de alguns
parâmetros.

| | On-premise (hoje) | AWS |
|---|---|---|
| Onde | Servidor Ubuntu, `192.168.99.5`, MicroK8s single node | EC2 single node (decidido) → EKS (adiante) |
| Acesso | **SSH** para o host; `kubectl` do Mac | **SSM Session Manager** — sem porta 22 aberta |
| Kubernetes | MicroK8s 1.35.6 | idem, no EC2 — ou EKS, em outro momento |
| Emulador de AWS | **Floci** em `192.168.99.5:4566` | não existe: desaparece da topologia |
| Credencial | `AWS_ACCESS_KEY_ID=test` / `…=test` (valor fixo, o emulador não valida) | real, **fora do Git**, vinda do ambiente |
| `--endpoint-url` | obrigatório em todo comando `aws` | nunca |
| `skip_credentials_validation` e os outros 3 | `true` | `false` |

### Por que MicroK8s, e não kubeadm

Porque ele **vem com os addons**. Num único node de laboratório, o que se quer é
DNS, storage e registry funcionando sem montar cada peça — e as peças que
importam para o estudo (Ingress, service mesh, observabilidade, GitOps) entram
por Helm, via ArgoCD, declaradas. A decisão de evoluir para EKS está registrada
como **outro momento**, não como pendência.

### O ponto que exige atenção na mudança

Os quatro `skip_*` do provider Terraform existem **por causa do emulador**. No
ambiente AWS eles têm de voltar a `false`: pular a validação de credencial contra
a AWS de verdade é o caminho mais curto para um `apply` que "funciona" e não
criou o que deveria. Por isso eles são **variáveis com padrão `false`** em
`terraform/iam-users/variables.tf`, e o `tfvars` do Floci é que os liga.

---

## 2. O host de operação

O Terraform não roda na máquina de quem está olhando o painel. Ele roda num
**host de operação**, e esse host é pré-requisito:

| O que vive nele | Por quê |
|---|---|
| Terraform ≥ 1.3 | o `optional()` dos tipos do módulo exige 1.3 |
| Python 3 + `venv` | os scripts de bancada (provisioner, coletor de preços) |
| Credencial AWS no ambiente | nunca em arquivo versionado |
| O repositório clonado | a fonte da verdade é o Git, não a máquina |

### O substituto do bastion

O caminho tradicional seria um bastion com SSH aberto para a internet. Na AWS
existe substituto melhor, e é o que adotamos: **SSM Session Manager** — o agente
na instância fala com o serviço, a autorização é por IAM, e **nenhuma porta
precisa estar aberta**. O acesso fica auditável e não há chave para vazar.

Consequência de custo, que entra na calculadora: com **subnet pública e security
group sem a porta 22**, não é preciso NAT Gateway nem VPC endpoint para o agente
do SSM alcançar o serviço. Um NAT custaria mais por semana do que o próprio host
de operação custa.

---

## 3. Marco zero — a ordem das coisas

1. **Credencial fora do Git.** Exportar no shell do host de operação. O
   provider não tem `access_key`/`secret_key` no código, de propósito: é o que
   permite o mesmo stack rodar contra o Floci e contra a AWS.
2. **Decidir onde vive o estado** (ver §5 — hoje é local, e isso está declarado).
3. `terraform -chdir=terraform/iam-users init`
4. `terraform -chdir=terraform/iam-users plan` — conferir antes de aplicar
5. `terraform -chdir=terraform/iam-users apply`
6. O que **não** é AWS (cluster, ArgoCD, aplicações) sobe por GitOps, não por
   Terraform.
7. A calculadora lê o preço da fonte oficial e diz quanto isto custa (§6).

---

## 4. O que está declarado em Terraform

Stack único em `terraform/iam-users/` — decisão consciente: um stack, não um por
camada, porque o esforço de trocar de nuvem aqui é o que importa, não a
segregação.

| Módulo | O que cria |
|---|---|
| `modules/s3` | os buckets do laboratório, com versionamento, SSE e ciclo de vida por bucket |
| `modules/iam` | usuários, roles e policies — incluindo a role do publisher do TechDocs |
| `modules/sso` | a instância do IAM Identity Center é **descoberta** (`aws_ssoadmin_instances`), não digitada |
| `modules/lambda` | a função do CAF e o empacotamento |

Os buckets são um **mapa** em `terraform.tfvars`, com a **chave sendo o nome
físico do bucket**:

```hcl
buckets = {
  "resilience-techdocs" = { versioning_status = "Enabled", sse_algorithm = "AES256", transition_days = 30, storage_class = "ONEZONE_IA" }
}
```

Chave estranha em bucket existente recriaria o recurso — foi para isso que os
blocos `moved` do módulo existem, e é por isso que a data de criação do bucket
(2026-09-16) é a verificação que fecha a conta, não o `plan`.

---

## 5. O que NÃO dá em Terraform — e o que fazemos no lugar

Esta seção é a razão de o documento existir. São os pré-requisitos que **não
podem** ser declarados, e ficam aqui em vez de ficarem na cabeça de alguém.

### 5.1 Credencial do provider

Vem do **ambiente**, sempre. Não é escolha de estilo: é o que permite que o mesmo
código aponte para o emulador e para a AWS sem alterar uma linha.

```bash
# Floci (emulador)
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1

# AWS de verdade: credencial real, no ambiente, nunca no repositório
```

**Controle negativo que vale registrar:** sem as variáveis, o provider falha com
`No valid credential sources found` — o erro parece problema de permissão e é só
variável faltando.

### 5.2 O backend do estado

Hoje o estado é **local** (`env/dev/terraform.tfstate`, gitignored, correto) e
existe só no disco de quem rodou.

Isso é aceitável num laboratório com um operador, e está **declarado**: a
consequência é que *a memória do ambiente não está no Git*. Um clone limpo
planeja, mas não conhece o que já existe.

Na AWS, a decisão muda — e aí aparece o ovo e a galinha clássico: um backend
remoto exige que o **bucket e o mecanismo de lock já existam** antes do
`terraform init`. Esse é o exemplo canônico de pré-requisito que o Terraform não
resolve sozinho: o recurso que guarda o estado não pode ser criado pelo estado
que ele guarda.

### 5.3 O bootstrap do host

O que falta para a história fechar: **subir o host do zero** (Ubuntu, MicroK8s e
addons, Docker, Floci) de forma declarada. Hoje isso está documentado — e
**documentado não é declarado**: não há script nem compose versionado.

O caminho aceito é `null_resource` com `local-exec`/`remote-exec` (script shell
interpolado dentro do `apply`), **ou** Ansible. A escolha está **adiada de
propósito** e não será tomada por conta própria.

---

## 6. A calculadora: quanto custa

No cluster: **https://calculadora.local** · contrato da API em **`/api/docs`**

```console
$ make -C apps/calculadora tabela

  Região: us-east-1 (US East (N. Virginia))   Janela: 168 h
  Fonte dos preços (lista oficial AWS): AmazonEC2 2026-09-18T21:27:57Z, …

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

**Como o número é produzido:** ele não foi digitado. Vem da
[AWS Bulk Price List](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json)
— pública, sem credencial — através de `apps/calculadora/buscar_precos.py`, e o
snapshot carrega a `publicationDate` publicada pela própria AWS. Cada linha da
tabela tem SKU e `usageType` para ser auditada.

### O que o número assume

- **Single node, sem alta disponibilidade.** Declarado, não descuidado: numa
  janela de apresentação o segundo node não paga o próprio custo.
- **On-demand.** Em 7 dias, Reserved e Savings Plans não se aplicam — os dois
  exigem compromisso de 1 a 3 anos.
- **Sem NAT Gateway e sem VPC endpoint**, porque o acesso é por SSM (§2).
- **`GB-Mo` pro-rateado por hora** (730 h/mês), que é como a AWS cobra disco.
- **Região `us-east-1`.** O seletor da tela lista as **106** regiões que a AWS
  publica, mas só a coletada tem preço: oferecer as outras seria inventar número.

### Como recalcular

```bash
make -C apps/calculadora snapshot   # 288 MB do arquivo do EC2, roda no host de operação
make -C apps/calculadora tabela     # a mesma conta que o painel faz
```

O passo é caro e raro **de propósito**: o snapshot fica versionado e a aplicação
serve instantâneo. E o refresh roda no host de operação — onde já existem Python
e venv —, não na máquina de quem abre o painel.

---

## 7. Checklist do marco zero

- [ ] Credencial AWS disponível **no ambiente** do host de operação (nunca no Git)
- [ ] Terraform ≥ 1.3 e Python 3 com `venv` no host
- [ ] Repositório clonado — é dele que o ArgoCD sincroniza
- [ ] Backend do estado decidido e consciente (§5.2)
- [ ] Acesso ao host por **SSM Session Manager**, sem porta 22 aberta
- [ ] `terraform init` → `plan` → `apply` em `terraform/iam-users/`
- [ ] `skip_credentials_validation` e os outros três em `false` **no ambiente AWS**
- [ ] Buckets conferidos pela data de criação, não só pelo `plan`
- [ ] Calculadora recalculada com snapshot fresco (`make snapshot`)
- [ ] Backlog registrado e não esquecido: bootstrap do host (§5.3) e EKS
