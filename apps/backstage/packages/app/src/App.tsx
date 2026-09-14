import { createApp } from '@backstage/frontend-defaults';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import searchPlugin from '@backstage/plugin-search'; // <-- Importa o PLUGIN de busca
import { navModule } from './modules/nav';
import { homeModule } from './modules/home';

export default createApp({
  // Adiciona o searchPlugin ao array de features
  features: [catalogPlugin, searchPlugin, navModule, homeModule],
});
