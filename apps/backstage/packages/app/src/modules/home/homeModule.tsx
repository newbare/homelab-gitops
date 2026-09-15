import { createFrontendModule, PageBlueprint } from '@backstage/frontend-plugin-api';
import { HomePageWidgetBlueprint } from '@backstage/plugin-home-react/alpha';
import { HomepageCompositionRoot } from '@backstage/plugin-home';
import { MarkdownContent } from '@backstage/core-components';

const content = `
## Welcome to Backstage! 👋

Backstage is your developer portal — a single place to manage all your
software, services, and documentation.

### Quick Start

- **Explore the catalog** — Browse all your organization's software in
  the [Software Catalog](/catalog)
- **Create something new** — Use a [Software Template](/create) to
  scaffold a new project in minutes
- **Read the docs** — Find technical documentation for any service
  right from its catalog page

### Helpful Links

- [Backstage Documentation](https://backstage.io/docs)
- [Customizing Your Homepage](https://backstage.io/docs/getting-started/homepage)
- [Adding Plugins](https://backstage.io/docs/plugins)
- [Contributing](https://github.com/backstage/backstage/blob/master/CONTRIBUTING.md)
`;

const gettingStartedWidget = HomePageWidgetBlueprint.make({
  name: 'getting-started',
  params: {
    name: 'GettingStarted',
    title: 'Getting Started',
    description: 'Tips and links to help you get started with Backstage',
    components: async () => ({
      Content: () => <MarkdownContent content={content} />,
    }),
  },
});

// ⬇️ NOVO: registra a rota /home
const homePage = PageBlueprint.make({
  params: {
    path: '/home',
    title: 'Home',
    loader: async () => <HomepageCompositionRoot />,
  },
});

export const homeModule = createFrontendModule({
  pluginId: 'home',
  extensions: [homePage, gettingStartedWidget],
});
