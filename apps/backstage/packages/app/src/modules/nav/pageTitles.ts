import { createFrontendModule } from '@backstage/frontend-plugin-api';

import catalogPlugin from '@backstage/plugin-catalog/alpha';
import catalogGraphPlugin from '@backstage/plugin-catalog-graph/alpha';
import catalogImportPlugin from '@backstage/plugin-catalog-import/alpha';
import notificationsPlugin from '@backstage/plugin-notifications/alpha';
import scaffolderPlugin from '@backstage/plugin-scaffolder/alpha';
import techdocsPlugin from '@backstage/plugin-techdocs/alpha';
import userSettingsPlugin from '@backstage/plugin-user-settings/alpha';
import visualizerPlugin from '@backstage/plugin-app-visualizer';

/**
 * Traduz os TÍTULOS DAS PÁGINAS — e, por consequência, os rótulos do menu.
 *
 * ---------------------------------------------------------------------------
 * POR QUE ISSO É NECESSÁRIO (o i18n não alcança aqui)
 * ---------------------------------------------------------------------------
 * O título de uma página NÃO é chave de tradução. Ele é passado no `make()` do
 * blueprint, em tempo de carga do plugin:
 *
 *   // @backstage/plugin-catalog/dist/alpha.esm.js
 *   PageBlueprint.make({
 *     name: 'catalog',
 *     params: { title: 'Catalog', ... }     // ← literal, sem `titleKey`
 *   })
 *
 * Confirmado: `grep -rn 'titleKey' --include='*.d.ts' node_modules/@backstage/`
 * não devolve nada nesta versão. E `app.extensions` no app-config não resolve:
 * aceita apenas `attachTo`, `disabled` e `config` — e o data ref `core.title`
 * não tem schema (`createExtensionDataRef().with({ id: "core.title" })`).
 *
 * ---------------------------------------------------------------------------
 * COMO FUNCIONA O OVERRIDE
 * ---------------------------------------------------------------------------
 * A API `OverridableExtensionDefinition.override({ params })` devolve uma NOVA
 * definição da mesma extensão, com os params mesclados. O `createFrontendModule`
 * com o `pluginId` de destino é quem INSTALA esse override — é o substituto
 * oficial do `createExtensionOverrides`, removido em v0.9.0.
 *
 * ---------------------------------------------------------------------------
 * POR QUE O MENU MUDA JUNTO (e a pegadinha que quase estraguei)
 * ---------------------------------------------------------------------------
 * O `AppNav` decide o rótulo assim:
 *
 *   const hasExplicitPageTitle = resolvedTitle !== undefined
 *                              && resolvedTitle !== pluginTitle
 *                              && resolvedTitle !== pluginId;
 *   const title = hasExplicitPageTitle
 *     ? resolvedTitle                       // ← título da página
 *     : matchingNavItem?.title ?? pluginTitle ?? pluginId;
 *
 * Como o título da página hoje é IGUAL ao título do plugin ("Catalog" nos
 * dois), `hasExplicitPageTitle` é `false` e vale o `pluginTitle`.
 *
 * ⚠️ Isso significa que trocar SÓ o título do plugin (`withOverrides({title})`)
 * NÃO funciona: o `resolvedTitle` (literal inglês) passaria a divergir do
 * `pluginTitle` novo, `hasExplicitPageTitle` viraria `true` e o inglês
 * voltaria — pelo caminho mais longo. Tem de ser o título da PÁGINA.
 *
 * Traduzindo o `params.title` da página, os três lugares acompanham: o item do
 * menu, o `<h1>` da página e o breadcrumb.
 *
 * ---------------------------------------------------------------------------
 * O QUE **NÃO** ESTÁ AQUI
 * ---------------------------------------------------------------------------
 * - `page:home` → fica "Home" por decisão do projeto.
 * - `page:api-docs` → fica "APIs" (o nome é a sigla; o conteúdo é traduzido).
 *
 * Os ids foram extraídos do próprio app (página /visualizer → Tree), não
 * chutados: `page:catalog`, `page:scaffolder`, `page:catalog-graph`,
 * `page:catalog-import`, `page:techdocs`, `page:notifications`,
 * `page:app-visualizer`, `page:user-settings`.
 */
export const pageTitleOverrides = [
  createFrontendModule({
    pluginId: 'catalog',
    extensions: [
      catalogPlugin
        .getExtension('page:catalog')
        .override({ params: { title: 'Catálogo' } }),
    ],
  }),
  createFrontendModule({
    pluginId: 'scaffolder',
    extensions: [
      scaffolderPlugin
        .getExtension('page:scaffolder')
        .override({ params: { title: 'Criar' } }),
      // Abas internas da página Criar — também são títulos literais.
      scaffolderPlugin
        .getExtension('sub-page:scaffolder/tasks')
        .override({ params: { title: 'Tarefas' } }),
      scaffolderPlugin
        .getExtension('sub-page:scaffolder/actions')
        .override({ params: { title: 'Actions' } }),
      scaffolderPlugin
        .getExtension('sub-page:scaffolder/editor')
        .override({ params: { title: 'Editor de template' } }),
      scaffolderPlugin
        .getExtension('sub-page:scaffolder/templating-extensions')
        .override({ params: { title: 'Extensões de template' } }),
    ],
  }),
  createFrontendModule({
    pluginId: 'catalog-graph',
    extensions: [
      catalogGraphPlugin
        .getExtension('page:catalog-graph')
        .override({ params: { title: 'Grafo do catálogo' } }),
    ],
  }),
  createFrontendModule({
    pluginId: 'catalog-import',
    extensions: [
      catalogImportPlugin
        .getExtension('page:catalog-import')
        .override({ params: { title: 'Registrar componente existente' } }),
    ],
  }),
  createFrontendModule({
    pluginId: 'techdocs',
    extensions: [
      techdocsPlugin
        .getExtension('page:techdocs')
        .override({ params: { title: 'Documentação' } }),
    ],
  }),
  createFrontendModule({
    pluginId: 'notifications',
    extensions: [
      notificationsPlugin
        .getExtension('page:notifications')
        .override({ params: { title: 'Notificações' } }),
    ],
  }),
  createFrontendModule({
    pluginId: 'app-visualizer',
    extensions: [
      visualizerPlugin
        .getExtension('page:app-visualizer')
        .override({ params: { title: 'Visualizador' } }),
      visualizerPlugin
        .getExtension('sub-page:app-visualizer/tree')
        .override({ params: { title: 'Árvore' } }),
      visualizerPlugin
        .getExtension('sub-page:app-visualizer/details')
        .override({ params: { title: 'Detalhes' } }),
      visualizerPlugin
        .getExtension('sub-page:app-visualizer/text')
        .override({ params: { title: 'Texto' } }),
    ],
  }),
  createFrontendModule({
    pluginId: 'user-settings',
    extensions: [
      userSettingsPlugin
        .getExtension('page:user-settings')
        .override({ params: { title: 'Configurações' } }),
      // Abas internas de Configurações.
      userSettingsPlugin
        .getExtension('sub-page:user-settings/general')
        .override({ params: { title: 'Geral' } }),
      userSettingsPlugin
        .getExtension('sub-page:user-settings/auth-providers')
        .override({ params: { title: 'Provedores de autenticação' } }),
      userSettingsPlugin
        .getExtension('sub-page:user-settings/feature-flags')
        .override({ params: { title: 'Feature flags' } }),
    ],
  }),
];
