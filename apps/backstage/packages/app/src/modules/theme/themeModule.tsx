import { createFrontendModule } from '@backstage/frontend-plugin-api';
import { ThemeBlueprint } from '@backstage/plugin-app-react';
import {
  UnifiedThemeProvider,
  createUnifiedTheme,
  palettes,
  genPageTheme,
} from '@backstage/theme';
import LightIcon from '@material-ui/icons/WbSunny';

// ⬇️ Define o theme Resilience Cloud
const resilienceLightTheme = createUnifiedTheme({
  palette: {
    ...palettes.light,
    primary: {
      main: '#FF9900',
    },
    secondary: {
      main: '#1a202c',
    },
    background: {
      default: '#f7fafc',
      paper: '#ffffff',
    },
    navigation: {
      background: '#ffffff',
      indicator: '#FF9900',
      color: '#1a202c',
      selectedColor: '#FF9900',
      navItem: {
        hoverBackground: '#f7fafc',
      },
    },
  },
  // ⬇️ NOVO: sobrescreve os pageThemes (banners coloridos)
  pageTheme: {
    home: genPageTheme({
      colors: ['#FF9900', '#e68900'],
      shape: 'wave',
    }),
    documentation: genPageTheme({
      colors: ['#FF9900', '#e68900'],
      shape: 'wave',
    }),
    tool: genPageTheme({
      colors: ['#FF9900', '#e68900'],
      shape: 'wave',
    }),
    service: genPageTheme({
      colors: ['#FF9900', '#e68900'],
      shape: 'wave',
    }),
    website: genPageTheme({
      colors: ['#FF9900', '#e68900'],
      shape: 'wave',
    }),
    library: genPageTheme({
      colors: ['#FF9900', '#e68900'],
      shape: 'wave',
    }),
    other: genPageTheme({
      colors: ['#FF9900', '#e68900'],
      shape: 'wave',
    }),
    app: genPageTheme({
      colors: ['#FF9900', '#e68900'],
      shape: 'wave',
    }),
    apis: genPageTheme({
      colors: ['#FF9900', '#e68900'],
      shape: 'wave',
    }),
  },
  components: {
    MuiListItem: {
      styleOverrides: {
        root: {
          color: '#1a202c',
        },
      },
    },
    MuiListItemIcon: {
      styleOverrides: {
        root: {
          color: '#1a202c',
        },
      },
    },
    MuiListItemText: {
      styleOverrides: {
        primary: {
          color: '#1a202c',
        },
      },
    },
    MuiSvgIcon: {
      styleOverrides: {
        root: {
          color: '#1a202c',
        },
      },
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