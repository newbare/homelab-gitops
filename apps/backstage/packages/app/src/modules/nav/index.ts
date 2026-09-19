import { createFrontendModule } from '@backstage/frontend-plugin-api';
import { SidebarContent } from './Sidebar';

export const navModule = createFrontendModule({
  pluginId: 'app',
  extensions: [SidebarContent],
});

/**
 * Overrides de título das páginas (e, com eles, os rótulos do menu).
 *
 * Separado do `navModule` de propósito: aquele mora no plugin `app` (é o
 * sidebar), este instala overrides em OUTROS plugins — um módulo por
 * `pluginId`, porque um módulo só pode ter um dono.
 */
export { pageTitleOverrides } from './pageTitles';
