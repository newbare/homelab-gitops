# Anatomia da definição oficial (o insumo do F3 e da fórmula do F4)

Documento de **investigação medida** em 2026-09-20, antes de escrever o F3. Ele
existe porque a leitura da definição oficial mudou duas coisas que o plano dava
como certas — e uma delas era o maior risco em aberto do projeto.

Nada aqui é dedução: cada trecho abaixo foi lido do JSON real, e o que é hipótese
está marcado como hipótese.

---

## 1. O caminho dentro da definição

```
definição (serviceDefinitionLocation)      ex.: aWSLambda, awsKeyManagementService
  ├─ serviceCode · serviceName · slug · version · type · layout · costType
  ├─ regions ....................... lista de regiões (KMS: 25 · Lambda: **vazia**)
  ├─ mappingDefinitions ............ [ { mappingDefinitionName, mappingDefinitionURL } ]
  └─ templates[] ◄────────────────── AQUI mora o formulário (um serviço tem N)
        ├─ id · title · description · helpUrl
        ├─ mappingFromTemplate ..... herda o mapeamento de outro template
        └─ cards[]
              ├─ title · helpText · helpUrl · bodyText · displayIf
              ├─ inputSection.components[]   ◄── OS CAMPOS **e** OS PREÇOS
              └─ mathsSection[].components[] ◄── A FÓRMULA
```

⚠️ **`fields` e `cards` não existem no topo da definição.** Quem tem `cards` é o
**template**. Eu havia anotado "5 cards e ~42 campos" para o Lambda sem o
caminho completo — o caminho completo é `templates[].cards[]`.

Medido:

| serviço | versão | templates | cards por template | `regions` |
|---|---|---|---|---|
| `awsKeyManagementService` | 0.0.20 | 1 (`kms`) | 1 ("Service settings") | 25 |
| `aWSLambda` | 0.0.146 | 2 (`lambdaWithFreeTier`, `lambdaWithoutFreeTier`) | 5 cada | **vazia** |

O Lambda é o caso que dá a medida do problema: **um serviço, dois templates** — e
o primeiro declara `mappingFromTemplate: lambdaWithoutFreeTier`, ou seja, herda o
mapeamento do segundo. `regions` vazio no Lambda não significa "sem região": o
seletor dele vem do mapa de preço, não da definição.

---

## 2. Os campos, e o que cada um carrega

O card do KMS tem **12 componentes** em `inputSection`: **6 de campo e 6 de preço**.
Os dois tipos vêm na MESMA lista — e é isso que engana quem lê rápido.

### 2.1 Componente de campo

```json
{
  "displayIf": { "exists": { "type": "meteredUnit",
                             "mappingDefinitionName": "kms",
                             "meteredUnit": "Encryption Key" } },
  "type": "input",
  "subType": "numericInput",
  "id": "numberOfCmk",
  "label": "Number of customer managed Customer Master Keys (CMK)",
  "displayInConfigSummary": true,
  "defaultValue": 5,
  "validations": { "required": false, "allowDecimals": false,
                   "minValue": 0, "maxValue": 10000000000 }
}
```

O que cada chave significa para o formulário:

| chave | para que serve |
|---|---|
| `id` | a chave do campo — é o `variableId` que a fórmula referencia |
| `type` + `subType` | como desenhar: `input/numericInput`, `input/dropdown`, `input/frequency`, `input/fileSize` |
| `label` | o rótulo humano |
| `defaultValue` | o valor inicial (o KMS sugere 5 chaves CMK) |
| `validations` | **é aqui que mora o "obrigatório"** — não existe campo `required` no topo; e vêm junto `minValue`, `maxValue` e `allowDecimals` |
| `displayInConfigSummary` | a oficial mostra este campo no resumo da configuração |
| `displayIf.exists.meteredUnit` | **o campo só aparece se aquele metered unit existir no preço** |

### 2.2 Componente de preço

```json
{
  "type": "pricing",
  "id": "cmkPrice",
  "label": "Price for CMK per month",
  "subType": "singlePricePoint",
  "mappingDefinitionName": "kms",
  "meteredUnit": { "allRegions": "Encryption Key" },
  "backwardCompatibility": { "hideCardWhenMissing": false }
}
```

Não é campo de entrada: é **um preço a resolver**. `subType: singlePricePoint`
indica preço único (o outro tipo visto na literatura é o escalonado). O
`meteredUnit` é um **nome** — `"Encryption Key"` — e é ele que aponta para o preço.

---

## 3. ★ A fórmula **está** na definição — o plano estava errado

O plano diz, na tabela de riscos:

> **A fórmula** — tenho as dimensões e os preços; **não tenho a aritmética** que os
> combina (ela vive no bundle do app, não na definição)

**Ela vive na definição.** O KMS prova:

```json
{
  "type": "maths",
  "subType": "basicMaths",
  "id": "cmkMonthlyCost",
  "operation": "multiplication",
  "operands": [
    { "variableId": "numberOfCmk", "variableUnitLabel": "CMKs", "required": true },
    { "variableId": "cmkPrice",   "variableUnitLabel": "[currency]", "required": true }
  ],
  "outputUnitLabel": "[currency] for CMKs",
  "decimalPlaces": 4
}
```

Leia-se: `cmkMonthlyCost = numberOfCmk × cmkPrice`. E o card do KMS tem **seis**
desses, um por dimensão:

```
cmkMonthlyCost                = numberOfCmk                × cmkPrice
symmetricRequestCost          = numberOfSymmetricRequests  × requestSymmetricPrice
asymmetricRequestCost         = numberOfAsymmetricRequestsExceptRsa2048 × requestAsymmetricPrice
asymmetricRsaRequestCost      = numberOfAsymmetricRsaRequests × requestAsymmetricRSAPrice
...                            (e os dois de GenerateDataKeyPair: ECC e RSA)
```

Os `operands` são de **dois tipos**, e a distinção é a chave de tudo:

- `variableId` que é **id de campo** (`numberOfCmk`) → valor digitado pelo usuário;
- `variableId` que é **id de componente de preço** (`cmkPrice`) → valor resolvido
  do mapa oficial.

O `outputUnitLabel` (`[currency] for CMKs`) e o `decimalPlaces: 4` dizem como
apresentar. **A aritmética não precisa ser escrita por nós** — precisa ser lida,
executada e conferida contra a oficial.

Isso não elimina o risco, ele muda de lugar: deixa de ser "inventar a conta" e
passa a ser "interpretar e executar `basicMaths`", com a mesma disciplina de
conferência que a F1 usou no preço.

---

## 4. O que continua faltando: o **nome** do metered unit → o **rateCode**

O elo que falta, e agora com o tamanho exato do problema:

```
definição      meteredUnit: { "allRegions": "Encryption Key" }     ← um NOME
mapa de preço  regions["US East (N. Virginia)"][<id opaco>] =
               { "rateCode": "NNYDKMC6UDJC5BNA.JRTCKXETXF.6YS6EN2CT7",
                 "price": "0.0000100000",
                 "RegionlessRateCode": "5IqyKzqZftmKSk_fiDfbuWXaObx-Wav6Zw9jM6bP60I" }
                                                                   ← nenhum NOME
```

Medido no mapa do KMS:

- **`sets` está VAZIO** (`0` entradas). Eu supus que a ponte estaria ali; não está.
- a chave de cada item da região **é igual ao `RegionlessRateCode`** — um id opaco,
  não derivado do nome por nada que eu tenha encontrado.
- o `manifest` do mapa tem `"esIndex": "plc-kms-usd-20260911124601"` — **um índice
  de Elasticsearch**. É assim que a oficial resolve nome → preço: num índice
  interno, que não é público.

Ou seja: a oficial publica o **nome** (na definição) e o **preço** (no mapa), e
faz a ligação num serviço interno nosso não temos.

### 4.1 A pista para fechar isso (ainda NÃO confirmada)

O repositório curado `aws-samples/sample-aws-pricing-calculator-mcp`
(`catalog/README.md`) documenta uma **terceira superfície**, por calc-id e região:

```
https://calculator.aws/pricing/2.0/meteredUnitMaps/<família>/USD/current/<calc-id>/<região-url-encoded>/primary-selector-aggregations.json
```

Nas palavras deles: *"for multi-template / multi-selector services (RDS, EC2,
Fargate), the calculator's frontend fetches a JSON file listing every valid
selector tuple before building the UI"*, e o exemplo dado é
`.../rds/USD/current/rds-postgresql-calc/US%20East%20(N.%20Virginia)/primary-selector-aggregations.json`.

**Hipótese (não medida):** esse arquivo é a ponte. Ele é por `calc-id`, e a
`<calc-id>` tem a forma das famílias que a F1 classificou como "mapas sem eixo de
região" (`rds-postgresql-calc`, `rds-mysql-calc`, `dedicatedhost-calc`…). Se for
isso, aquelas 47 famílias **não são um formato sem região** — são a mesma
informação servida por um caminho por região, e o que a F1/F2 tratou como "sem
eixo de região" ganha explicação.

O próximo passo é uma sonda de 20 segundos nesse URL (script pronto em
`/tmp/agregacoes.py`), que responde as duas perguntas de uma vez:

1. o arquivo traz os `meteredUnit` **com nome**?
2. a família `-calc` é a mesma coisa, servida por esse caminho?

Se a resposta for não, a saída honesta passa a ser: **casar por preço conferido**
(o catálogo curado traz `minimalConfig` auditado para 60 serviços, e os preços
públicos do KMS são conhecidos), sempre como *verificação* de um casamento
encontrado por outro caminho — nunca como o casamento em si. Foi um casamento por
semelhança de nome que produziu o erro do `AmazonS3` no Aurora.

---

## 5. O que isso muda no desenho

### 5.1 O schema precisa da dimensão `template`

`campo_servico (service_code, campo_id)` com `UNIQUE (service_code, campo_id)` —
como está no plano — **não representa o Lambda**: dois templates, e o mesmo
serviço. O formulário é por template, não por serviço. A rota também muda:

```
plano:  /servicos/{code}/campos
real:   /servicos/{code}/templates/{template_id}/campos
```

### 5.2 O que o `campo_servico` passa a guardar

| coluna do plano | o que a definição oferece |
|---|---|
| `campo_id` | `id` |
| `tipo` / `sub_tipo` | `type` / `subType` (`input/numericInput`) |
| `rotulo` | `label` |
| `opcoes` | **não existe no KMS** — só nos `dropdown`; verificar no Lambda antes de assumir forma |
| `obrigatorio` | `validations.required` (**aninhado**, não no topo) |
| `ordem` | a posição na lista de `components` |

E dois campos que o plano não previu e que fazem falta:

- **`default_value`** — sem ele, o formulário nasce vazio e o total nasce zero
  (a armadilha do "US$ 0 silencioso" do catálogo curado);
- **`metered_unit`** — o nome do metered unit que aquele campo consome
  (`displayIf.exists.meteredUnit`), que é o que permite dizer "este campo não tem
  preço publicado nesta região" **em vez de mostrar zero**.

### 5.3 O que o F4 passa a ser

Deixa de ser "escrever a fórmula de cada serviço" e passa a ser:

1. ler `mathsSection` e executar `basicMaths` (as operações vistas: `multiplication`);
2. resolver cada variável de preço (`type=pricing`) pelo `meteredUnit`;
3. conferir o total contra a oficial, como a F1 conferiu preço por `rateCode`.

O trabalho difícil diminui; o trabalho de **conferência** continua igual.

---

## 6. Como reproduzir

```bash
# 1. a estrutura da definição (topo, templates, cards)
python3 /tmp/inspecionar-definicao.py
python3 /tmp/inspecionar-templates.py

# 2. o card do KMS inteiro: campos, precos e a formula
python3 /tmp/abrir-card-kms.py        # inputSection + mathsSection
python3 /tmp/componentes-kms.py       # os 12 componentes, campo x preço

# 3. o mapa de preco: sets vazio e o esIndex
python3 /tmp/inspecionar-sets.py
python3 /tmp/maths-kms.py             # manifest do mapa + a formula completa

# 4. a sonda que ainda falta rodar (a ponte nome -> rateCode)
python3 /tmp/agregacoes.py
```
