# Jornada — Fase 8 (Polish Visual)

Documentação retroativa da Fase 8 do Backstage — aplicação da identidade
visual da Resilience Cloud + resolução de pendências da Fase 7.

Cobre o período de **16/09/2026, 06:00** até **16/09/2026, 13:24**
(~7h de trabalho).

## 🎯 Objetivo da Fase 8

Aplicar a **identidade visual da Resilience Cloud** ao Backstage e resolver
pendências deixadas na Fase 7:

- Logo Resilience Cloud na sidebar
- Favicon customizado (nuvem laranja)
- Título: "Resilience Cloud Portal"
- Theme visual (cores da marca: laranja `#FF9900`, navy `#1a202c`)
- **CSP** para liberar o widget "Random Joke"
- **Visit Tracking** para popular "Most Visited" / "Recently Visited"

## 📊 Timeline geral

| Etapa | Duração | Acumulado |
|---|---|---|
| 1. Setup + discussão inicial | 30 min | 0h30 |
| 2. Primeira tentativa de theme (CSS vars) | 1h | 1h30 |
| 3. Theme via MUI (`themeModule.tsx`) | 1h | 2h30 |
| 4. Debug do BUI (botões primários) | **2h** ⬅️ mais longo | 4h30 |
| 5. Recorte dos logos (Pillow) | 45 min | 5h15 |
| 6. Favicon + manifest | 30 min | 5h45 |
| 7. Banner `pageTheme` | 45 min | 6h30 |
| 8. Commit + PR + docs | 30 min | 7h00 |

**Total: ~7h**

## 🎬 Estado inicial (16/09/2026, 06:00)

O Backstage estava na Fase 7 concluída:

- ✅ Backstage funcional (v7)
- ✅ Home customizada na raiz
- ✅ 4 plugins (notifications, search, home, scaffolder)
- ⚠️ CSP bloqueando `official-joke-api.appspot.com`
- ⚠️ Visit Tracking desabilitado
- ❌ Sem identidade visual Resilience Cloud
- ❌ Logo padrão do Backstage

O objetivo era **transformar o Backstage genérico** no **Resilience Cloud
Portal**.

## 🔍 Investigação cronológica

### Etapa 1 — Setup + discussão inicial (30 min)

**Objetivo:** definir o escopo do polish.

**Decisões:**

1. **Cores da marca:** `#FF9900` (laranja AWS) + `#1a202c` (navy)
2. **Logo oficial:** `https://resiliencecloud.com.br/img/logo4.png`
3. **Escopo:**
   - Logo + favicon + título
   - Theme (cores)
   - CSP + Visit Tracking

**Criada a branch `feat/polish-fase-8`.**

### Etapa 2 — Primeira tentativa de theme (CSS vars) (1h)

**Abordagem:** criar `resilience-theme.css` com variáveis CSS do Backstage
UI (BUI):

```css
:root {
  --bui-accent-bg: #FF9900;
  --bui-accent-bg-hover: #e68900;
  --bui-accent-fg: #ffffff;
  --bui-bg-app: #f7fafc;
}
```

**Importado no `App.tsx`:**

```tsx
import './resilience-theme.css';
```

**Resultado:** ❌ **NÃO FUNCIONOU.** Os botões continuaram azuis.

**Causa descoberta depois:** o BUI carrega o CSS dele **DEPOIS** do nosso, e
usa `@layer` (CSS Cascade Layers) que **sobrepõe** estilos fora do layer.

### Etapa 3 — Theme via MUI (`themeModule.tsx`) (1h)

**Abordagem:** usar `@backstage/theme` com `createUnifiedTheme` e
registrar via `ThemeBlueprint`.

**Código inicial:**

```tsx
// apps/backstage/packages/app/src/modules/theme/themeModule.tsx
import { ThemeBlueprint } from '@backstage/plugin-app-react';
import { createUnifiedTheme, palettes, UnifiedThemeProvider } from '@backstage/theme';
import LightIcon from '@material-ui/icons/WbSunny';

const resilienceLightTheme = createUnifiedTheme({
  palette: {
    ...palettes.light,
    primary: { main: '#FF9900' },
    secondary: { main: '#1a202c' },
    navigation: {
      background: '#ffffff',
      indicator: '#FF9900',
      color: '#1a202c',
      selectedColor: '#FF9900',
    },
  },
});

const ResilienceLightTheme = ThemeBlueprint.make({
  name: 'resilience-light',
  params: {
    theme: {
      id: 'resilience-light',
      title: 'Resilience Light',
      variant: 'light',
      icon: <LightIcon />,
      Provider: ({ children }) => (
        <UnifiedThemeProvider theme={resilienceLightTheme}>
          {children}
        </UnifiedThemeProvider>
      ),
    },
  },
});

export const themeModule = createFrontendModule({
  pluginId: 'app',
  extensions: [ResilienceLightTheme],
});
```

**Resultado:** ✅ **FUNCIONOU PARCIALMENTE.**

- ✅ Sidebar clara (branca)
- ✅ Texto da sidebar navy (após overrides MUI)
- ✅ Item ativo laranja
- ⚠️ **Botões primários do BUI continuaram azuis**

**Descoberta:** o Backstage tem **DOIS sistemas de UI** coexistindo:

| Sistema | Componentes | Theming |
|---|---|---|
| **MUI** | Sidebar, links, a maioria dos plugins | JS (`UnifiedThemeProvider`) |
| **BUI** | Botões primários, banners, novos componentes | CSS vars |

**O botão "+ Create"** é do **BUI** — por isso não pegou o theme do MUI.

### Etapa 4 — Debug do BUI (2h) ⬅️ mais longo

**Sintoma:** o botão "+ Create" do Catalog continuava **azul `#9CC9FF`**
mesmo após:
- Setar `--bui-accent-bg` no `:root`
- Injetar via JS no `<html>`
- Setar `.bui-ButtonLink[data-variant='primary']`

**Investigação (via F12 → Console + Elements):**

1. **Inspecionar o botão** → classe `bui-ButtonLink` com
   `data-variant="primary"`
2. **Ver o CSS do BUI** no DevTools:

```css
.ButtonLink_bui-ButtonLink__053e4cbdce[data-variant='primary'] {
    --bg: var(--bui-bg-solid);              /* ⬅️ CHAVE! */
    --bg-hover: var(--bui-bg-solid-hover);
    --bg-active: var(--bui-bg-solid-pressed);
    --fg: var(--bui-fg-solid);
}
```

3. **Descobrir que o botão usa `--bui-bg-solid`**, não `--bui-accent-bg`.

**Tentativas que falharam:**

- ❌ Setar só `--bui-accent-bg`
- ❌ Injetar via JS só `--bui-accent-bg`
- ❌ Seletor `.ButtonLink_bui-ButtonLink__...` (hash muda a cada build)
- ❌ Usar `@layer bui` no CSS (o BUI usa `@layer base`, `@layer tokens`, `@layer utilities`)

**Consulta à documentação oficial:**

- **URL:** https://backstage.io/docs/conf/user-interface/
- **Descobertas cruciais:**
  - O BUI usa `[data-theme-mode='light']` (não `:root`)
  - `--bui-bg-solid` é a var dos botões primários
  - Dá pra customizar via `packages/app/src/styles.css` importado no `App.tsx`
  - Se o componente tem classe `bui-*`, use a abordagem BUI

**Solução final:**

```css
/* resilience-theme.css */
[data-theme-mode='light'] {
  --bui-bg-app: #f7fafc;
  --bui-bg-solid: #FF9900;
  --bui-fg-solid: #ffffff;
  --bui-fg-primary: #1a202c;
  --bui-fg-secondary: #4a5568;
  --bui-border-1: #e2e8f0;
  --bui-border-2: #cbd5e0;
}

/* Ataque direto ao botão */
.bui-ButtonLink[data-variant='primary'],
a[data-variant='primary'],
button[data-variant='primary'] {
  background-color: #FF9900 !important;
  color: #ffffff !important;
}
```

**Resultado:** ✅ Botão "+ Create" ficou **laranja**.

### Etapa 5 — Recorte dos logos (Pillow) (45 min)

**Objetivo:** recortar o logo oficial (`logo4.png`, 431x328) em 2 versões:

1. **Logo completo** (sidebar aberta) — 400x304
2. **Só a nuvem** (sidebar colapsada) — 431x220

**Problema:** `magick` (ImageMagick) não estava instalado, e o `brew
install` no **macOS Intel** demora muito (compila do zero).

**Solução:** usar **Pillow via venv**:

```bash
python3 -m venv /tmp/venv-pil
source /tmp/venv-pil/bin/activate
pip install Pillow

python <<'EOF'
from PIL import Image
img = Image.open('logo-resilience.png')
print(f"Original: {img.size}")
# Recorta a nuvem (topo)
icon = img.crop((0, 0, 431, 220))
icon.save('logo-resilience-icon.png')
# Redimensiona o logo completo
full = img.resize((400, int(400 * img.size[1] / img.size[0])))
full.save('logo-resilience-full.png')
EOF

deactivate
rm -rf /tmp/venv-pil
```

**Iteração:** o recorte inicial (`200` de altura) cortou parte da nuvem.
Ajustado pra `220`.

### Etapa 6 — Favicon + manifest (30 min)

**Geração dos favicons** via Pillow (mesmo venv):

```python
sizes = {
    'favicon-16x16.png': 16,
    'favicon-32x32.png': 32,
    'apple-touch-icon.png': 180,
    'android-chrome-192x192.png': 192,
    'android-chrome-512x512.png': 512,
}
for filename, size in sizes.items():
    resized = square.resize((size, size), Image.LANCZOS)
    resized.save(filename)
square.save('favicon.ico', sizes=[(16, 16), (32, 32), (48, 48)])
```

**Atualização do `manifest.json`:**

```json
{
  "short_name": "Resilience",
  "name": "Resilience Cloud Portal",
  "theme_color": "#FF9900",
  "background_color": "#ffffff"
}
```

**Resultado:** ✅ Favicon laranja na aba do browser.

### Etapa 7 — Banner `pageTheme` (45 min)

**Sintoma:** os banners das páginas (Catalog Graph, Register Existing)
continuavam com o **gradiente verde** padrão do Backstage.

**Investigação (F12 → Elements):**

- O banner é um `<header class="jss4-7831">` com `background-image` =
  **SVG inline** (`data:image/svg+xml,...`)
- Isso é o **`pageTheme`** do Backstage

**Solução:** sobrescrever o `pageTheme` no `themeModule.tsx`:

```typescript
import { genPageTheme } from '@backstage/theme';

const resilienceLightTheme = createUnifiedTheme({
  palette: { /* ... */ },
  pageTheme: {
    home: genPageTheme({ colors: ['#FF9900', '#e68900'], shape: 'wave' }),
    documentation: genPageTheme({ colors: ['#FF9900', '#e68900'], shape: 'wave' }),
    tool: genPageTheme({ colors: ['#FF9900', '#e68900'], shape: 'wave' }),
    // ... outros 7 themeIds
  },
});
```

**Resultado:** ✅ Banners ficaram laranja.

**Ajuste posterior:** o texto do banner (branco) ficou **invisível** sobre
o laranja. Corrigido com:

```css
/* resilience-theme.css */
header .MuiTypography-h1,
header .MuiTypography-root {
  color: #1a202c !important;  /* Texto preto */
}
```

**Resultado final:** ✅ Banner laranja + texto preto (contraste perfeito).

### Etapa 8 — Commit + PR + docs (30 min)

**Commit:**

```
679e588 feat(backstage): fase 8 — polish (theme Resilience, logos, favicon, CSP, visit tracking)
```

**PR #2:** mergeado na `main` (`2aae4dc`).

**18 arquivos modificados, 235 inserções.**

---

## 🚧 Becos sem saída

### 1. Setar apenas `--bui-accent-bg`

**O que tentamos:** CSS vars com `--bui-accent-bg` no `:root`.

**O que deu errado:** o BUI usa `--bui-bg-solid` pra botões primários.
`--bui-accent-bg` afeta outros componentes.

### 2. Injetar CSS via JavaScript

**O que tentamos:** `document.documentElement.style.setProperty(...)` no
`App.tsx`.

**O que deu errado:** as vars são aplicadas no `<html>`, mas o BUI aplica
o tema no `<body>` (via `data-theme-mode`). **O `<body>` sobrescreve.**

### 3. Usar `@layer bui`

**O que tentamos:** colocar o CSS dentro de `@layer bui`.

**O que deu errado:** o BUI usa **3 layers** (`base`, `tokens`,
`utilities`), não `bui`. E `@layer` tem regras complexas de prioridade.

### 4. Usar o hash da classe `.ButtonLink_bui-ButtonLink__053e4cbdce`

**O que tentamos:** seletor CSS direto com o hash.

**O que deu errado:** o **hash muda a cada build** (é gerado por CSS
Modules). **Frágil.** Solução: usar `[data-variant='primary']`.

### 5. `brew install imagemagick`

**O que tentamos:** instalar ImageMagick via Homebrew.

**O que deu errado:** no **macOS Intel (A2251, 2020)**, o Homebrew não
distribui mais binários pré-compilados. **Compila do zero — demora
horas.** Solução: usar **Pillow via venv** (`python3 -m venv`).

### 6. `pip install Pillow` direto

**O que tentamos:** `python3 -m pip install --user Pillow`.

**O que deu errado:** macOS moderno usa **PEP 668** (externally-managed-
environment) e **bloqueia** instalações globais. Solução: **venv
temporário**.

## 🎓 Lições / Insights principais

### 1. Backstage tem DOIS sistemas de UI

| Sistema | Onde | Theming |
|---|---|---|
| **MUI (legacy)** | Sidebar, links, maioria dos plugins | JS (`UnifiedThemeProvider`) |
| **BUI (novo)** | Botões primários, banners, novos componentes | CSS vars (`--bui-*`) |

**Como identificar:** se o componente tem classe `bui-*`, use BUI. Se
tem `Mui*`, use MUI.

### 2. BUI usa `[data-theme-mode='light']`, não `:root`

O BUI aplica o tema no **`<body>`** com `data-theme-mode="light"`. As
CSS vars precisam estar dentro desse seletor.

### 3. `--bui-bg-solid` controla botões primários

Não é `--bui-accent-bg`. A doc oficial esclarece:

> `--bui-bg-solid` — This is used for main actions like **primary
> buttons**.

### 4. `genPageTheme` controla os banners

Os banners das páginas (Catalog Graph, Register, Home) usam o
`pageTheme` do `createUnifiedTheme`. **Cada `themeId` tem uma cor
padrão** (documentation = verde, home = laranja, etc).

Pra mudar, sobrescreve **todos os `themeId`s**.

### 5. O texto do banner é controlado à parte

O `genPageTheme` só muda o **fundo**. O **texto** usa
`theme.palette.primary.contrastText`. Se o fundo for laranja, o texto
padrão (branco) fica **invisível**. Solução: override CSS.

### 6. F12 + Inspecionar é essencial pra BUI

O **DevTools** mostra:
- As classes `bui-*`
- As CSS vars aplicadas
- A especificidade das regras
- O `style` inline do `<html>` e `<body>`

**Sem inspecionar, é tentativa e erro infinito.**

### 7. Documentação oficial economiza horas

**URL:** https://backstage.io/docs/conf/user-interface/

Confirmou tudo o que descobrimos "na marra" e revelou:
- `[data-theme-mode='light']`
- `--bui-bg-solid` para botões
- Estrutura de CSS files (`packages/app/src/styles.css`)

### 8. Cache do browser engana

Sempre **hard refresh** (`Cmd+Shift+R`). O Backstage tem cache agressivo
de CSS e JS.

### 9. Pillow via venv é o jeito no macOS moderno

`python3 -m venv /tmp/venv-pil` + `pip install Pillow` resolve sem
sofrimento. **Não tenta instalar globalmente** (PEP 668 bloqueia).

### 10. Contraste é essencial

Branco sobre laranja (`#FF9900`) tem contraste **~2.2:1** — abaixo do
mínimo WCAG (4.5:1). **Solução:** texto preto sobre laranja, ou fundo
escuro com texto branco.

## 📌 Resultado final da Fase 8

| Item | Antes (v7) | Depois (v19) |
|---|---|---|
| Logo | Backstage genérico | Resilience Cloud |
| Favicon | Backstage | Nuvem laranja |
| Título | "Homelab Developer Portal" | "Resilience Cloud Portal" |
| Sidebar | Dark padrão | Clara com texto navy |
| Botões primários | Azul | Laranja |
| Banner `pageTheme` | Verde | Laranja com texto preto |
| CSP (Random Joke) | ❌ Bloqueado | ✅ Funcionando |
| Visit Tracking | ❌ Desabilitado | ✅ Populando |
| Imagem | v7 | **v19** |

**Total de versões:** v7 → v19 (12 iterações)

## 📊 Estatísticas

| Métrica | Valor |
|---|---|
| **Duração** | ~7h |
| **Versões de imagem** | v7 → v19 (12 builds) |
| **Arquivos modificados** | 18 |
| **Linhas adicionadas** | 235 |
| **Becos sem saída** | 6 |
| **Insights capturados** | 10 |

## 🔗 Ver também

- [`00-contexto.md`](./00-contexto.md) — motivação e stack
- [`01-arquitetura.md`](./01-arquitetura.md) — componentes e fluxo
- [`02-jornada-fase-7.md`](./02-jornada-fase-7.md) — jornada anterior
- [`03-decisoes.md`](./03-decisoes.md) — ADRs
- [`04-runbook.md`](./04-runbook.md) — operações comuns
- [`05-troubleshooting.md`](./05-troubleshooting.md) — erros conhecidos
- [`06-referencias.md`](./06-referencias.md) — links úteis
- **[Backstage UI theming](https://backstage.io/docs/conf/user-interface/)** — doc oficial (crucial!)