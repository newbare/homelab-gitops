import { createApp } from '@backstage/frontend-defaults';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import * as plugins from './plugins';
import { navModule, pageTitleOverrides } from './modules/nav';
import { homeModule } from './modules/home';
import { themeModule } from './modules/theme';
import { authModule } from './modules/auth';
import { translationsModule } from './modules/translations';

import './resilience-theme.css';

export default createApp({
  features: [
    catalogPlugin,
    ...Object.values(plugins),
    navModule,
    homeModule,
    themeModule,
    authModule,
    translationsModule,
    // Traduz os títulos das páginas (menu, <h1> e breadcrumb).
    // Ver modules/nav/pageTitles.ts para o porquê de não ser via i18n.
    ...pageTitleOverrides,
  ],
});