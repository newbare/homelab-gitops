import { createFrontendModule } from '@backstage/frontend-plugin-api';
import { TranslationBlueprint } from '@backstage/plugin-app-react';
import resources from '../../translations/resources';

/**
 * Módulo que ensina o Backstage a falar português.
 *
 * ---------------------------------------------------------------------------
 * COMO O i18n FUNCIONA AQUI (leia antes de mexer)
 * ---------------------------------------------------------------------------
 * O Backstage não traz traduções prontas. Cada plugin declara um
 * `TranslationRef` — um contrato com as mensagens **em inglês** — e quem quiser
 * outro idioma fornece um `TranslationResource` para aquele ref.
 *
 * O que este módulo faz é registrar cada resource no app:
 *
 *   translations/resources.ts   (gerado pelo CLI)
 *        └─ createTranslationResource({ ref, translations: { pt: ... } })
 *                    │
 *                    ▼
 *   TranslationBlueprint.make({ params: { resource } })
 *                    │
 *                    ▼
 *   createFrontendModule({ pluginId: 'app' })   ← este arquivo
 *
 * ---------------------------------------------------------------------------
 * POR QUE `pluginId: 'app'`
 * ---------------------------------------------------------------------------
 * O `TranslationBlueprint` é restrito: a própria tipagem/descrição diz que ele
 * é "limited to use by the app plugin". Ou seja, os resources são registrados
 * no plugin `app`, e é a extensão `TranslationsApi` dele que os distribui.
 * Usar outro `pluginId` não funciona.
 *
 * ---------------------------------------------------------------------------
 * POR QUE `resources.map(...)`
 * ---------------------------------------------------------------------------
 * `resources.ts` é um ARRAY de resources — um por ref traduzido. Cada um vira
 * uma extensão do tipo `translation`:
 *
 *   home         → 30 mensagens  (widgets, diálogos, estados vazios)
 *   home-react   →  3 mensagens  (modal de configurações do cartão)
 *
 * Traduzir um ref novo é só criar o `messages/<id>.pt.json` e rodar de novo:
 *
 *   cd packages/app
 *   yarn backstage-cli translations import
 *
 * O `resources.ts` é regerado e este módulo passa a registrar o ref novo
 * sozinho — não precisa editar este arquivo.
 *
 * ---------------------------------------------------------------------------
 * ⚠️ GAP QUE CUSTOU UMA TELA BRANCA: o `name` do `make` é OBRIGATÓRIO NA PRÁTICA
 * ---------------------------------------------------------------------------
 * A primeira versão deste módulo era:
 *
 *   resources.map(resource => TranslationBlueprint.make({ params: { resource } }))
 *
 * Compila sem erro (`tsc` exit 0) e o bundle é gerado normalmente. Mas o app
 * NÃO carrega — aparece só o erro abaixo, no console do navegador:
 *
 *   Error: Module 'app' provided duplicate extensions: translation:app
 *
 * Motivo: sem `name`, o id da extensão vira `<kind>:<pluginId>` — o MESMO para
 * todos os resources. Com dois refs (`home` e `home-react`), o app registra
 * duas extensões chamadas `translation:app` e recusa subir.
 *
 * A correção usa o `id` que o próprio resource carrega (o id do `TranslationRef`):
 *
 *   translation:app/home
 *   translation:app/home-react
 *
 * ⚠️ Lição: `tsc` passar NÃO significa que o app sobe. Erro de duplicidade só
 * aparece em tempo de execução, e no console do BROWSER — não em `kubectl logs`,
 * porque o processo Node do backend está saudável. A verificação tem de incluir
 * abrir a tela.
 *
 * ---------------------------------------------------------------------------
 * ⚠️ O QUE ESTE MÓDULO **NÃO** TRADUZ
 * ---------------------------------------------------------------------------
 * Os títulos mais visíveis da interface NÃO passam por aqui, porque não são
 * chaves de tradução — são strings fixas no código dos plugins:
 *
 *   // @backstage/plugin-home/dist/alpha.esm.js
 *   name: "HomePageToolkit",
 *   title: "Toolkit",          ← literal, não é `titleKey`
 *
 * Isso inclui o item "Home" do menu e os títulos dos cartões da home
 * ("Toolkit", "World Clocks", "Random Joke", "Most Visited", ...).
 *
 * Nesta versão (`@backstage/frontend-plugin-api@0.18.0`) não existe `titleKey`,
 * e o `app.extensions` do app-config aceita apenas `attachTo`, `disabled` e
 * `config` — não `title`. Para mudar esses rótulos seria preciso re-declarar as
 * extensões via `createFrontendModule`, o que é outro trabalho.
 *
 * Ver docs/backstage/11-fase-12-i18n-pt-br.md para a investigação completa.
 */
export const translationsModule = createFrontendModule({
    pluginId: 'app',
    extensions: resources.map(resource =>
        TranslationBlueprint.make({
            name: resource.id,
            params: { resource },
        }),
    ),
});
