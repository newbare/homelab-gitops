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

## 4. O elo `meteredUnit` → preço: **RESOLVIDO** (este documento estava errado)

Eu escrevi aqui que a ligação só existia num Elasticsearch interno, porque a chave
do mapa me pareceu um "id opaco" e o `sets` estava vazio. **Estava errado.**

O componente de preço carrega o endereço do preço:

```json
{ "type": "pricing", "subType": "singlePricePoint", "id": "cmkPrice",
  "mappingDefinitionName": "kms",
  "meteredUnit": { "allRegions": "Encryption Key" } }
```

`meteredUnit.allRegions` **é a chave daquele metered unit no mapa** — não um nome a
traduzir. O lookup é direto:

```python
preco = mapa["regions"]["US East (N. Virginia)"][componente["meteredUnit"]["allRegions"]]
```

Medido, comparando cada componente de preço com as chaves reais do mapa:

| serviço | chaves no mapa | componentes de preço | `allRegions` que É chave |
|---|---|---|---|
| KMS | 12 | 6 | **6 de 6** |
| EventBridge | 21 | 13 | 12 de 13 |
| CloudWatch | 208 | 35 | 25 de 35 |
| SQS | 13 | 3 | 1 de 3 |
| Lambda | 571 | 38 | 10 de 38 |

O que me enganou: em alguns serviços o valor é legível (`"Encryption Key"`,
`"Lambda Edge-Requests"`) e em outros é um hash
(`"M8QATjZO9cUYQz1nWgksW5SL-Tdu9le7of2vMo9w"`). O **formato** muda; o
**significado** não. É o mesmo erro que a F1 cometeu com a família `s3`: concluir
não-existência a partir de leitura parcial.

De quebra, o mesmo teste mostrou um detalhe que a F2 já tratava por sorte: o mapa
do KMS tem **12 chaves para 6 rateCodes** — o mesmo rateCode aparece duas vezes,
sob chaves diferentes. A consolidação por rateCode da carga absorve isso, e o
portão confere que os preços repetidos são iguais (foram: a carga passou).

### 4.1 O que os 62% do Lambda que não casam realmente são

Não são buraco nem mistério: são componentes **sem** `meteredUnit.allRegions`. O
Lambda tem 38 componentes de preço em 2 templates, e a maioria não é de preço único
— é de preço **combinado** (o que o catálogo curado chama de `pricingComboV2` e
`tieredPricing`, onde o valor nasce da COMBINAÇÃO de seletores). Os que casam são
exatamente os `singlePricePoint`.

Então o F4 tem **dois formatos**, e não um:

| formato | como resolve | estado |
|---|---|---|
| `singlePricePoint` + `meteredUnit.allRegions` | lookup direto na chave | ✅ resolvido |
| combo / escalonado | ler a forma do componente e resolver a combinação | ⏳ a mapear |

Separá-los é o que evita o erro clássico: tratar combo como preço único devolveria
`KeyError` ou, pior, um preço plausível e errado.

### 4.2 A sonda das famílias `-calc`: respondida — e não era a ponte

```
.../meteredUnitMaps/rds/USD/current/rds-postgresql-calc/US%20East%20(N.%20Virginia)/primary-selector-aggregations.json
  → HTTP 200 · 162 KB · 1073 "aggregations", cada uma com
    selectors: { Deployment Option, Instance Type, vCPU, Memory, TermType }

.../meteredUnitMaps/kms/USD/current/kms/<região>/primary-selector-aggregations.json     → HTTP 404
.../meteredUnitMaps/lambda/USD/current/lambda/<região>/primary-selector-aggregations.json → HTTP 404
```

Duas conclusões, uma de cada sinal:

- **não é a ponte**: o conteúdo é combinação de seletor, não metered unit. E para
  KMS — que já estava resolvido pelo `allRegions` — a rota dá 404;
- **explica as 47 famílias `-calc`**: elas existem **por região**, sob um `calc-id`, e
  o que publicam ali é a lista das combinações VÁLIDAS de seletor. A classificação
  da F1 ("mapas sem eixo de região") descrevia corretamente o arquivo que eu baixei;
  o que faltava era saber o que esses arquivos **são**. Agora sei — e isso importa
  para o F4: esse arquivo é a fonte de "quais combinações a AWS precifica", que é o
  que impede o formulário de oferecer uma combinação que não tem preço.

### 4.3 O caminho honesto que ficou de reserva (não foi necessário)

Antes de achar o `allRegions`, o plano era casar o nome do metered unit contra o
`usagetype`/`productFamily` do Bulk Price List — atributos de máquina, publicados
por SKU. Medido no KMS, esse casamento funciona razoavelmente
(`…-KMS-Requests-Asymmetric-RSA_2048` ↔ "Asymmetric Requests RSA_2048"), mas **não
generaliza**: no Lambda os componentes não têm nome nenhum, têm chave. Fica
registrado como o que era — um plano B que a medição dispensou.

A lição que sobra, e que vale mais que o atalho: **o dado estava no lugar óbvio o
tempo todo** (a definição diz onde o preço mora; o mapa é indexado por isso), e eu
fui procurar num Elasticsearch que nunca vi. Se eu tivesse escrito código sobre a
hipótese do `esIndex`, teria construído uma ponte para lugar nenhum.

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
