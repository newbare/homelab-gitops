import {
    BackstageIdentityApi,
    OpenIdConnectApi,
    ProfileInfoApi,
    SessionApi,
} from '@backstage/core-plugin-api';
import { OAuth2 } from '@backstage/core-app-api';
import { SignInPage } from '@backstage/core-components';
import {
    ApiBlueprint,
    configApiRef,
    createApiRef,
    createFrontendModule,
    discoveryApiRef,
    oauthRequestApiRef,
} from '@backstage/frontend-plugin-api';
import { SignInPageBlueprint } from '@backstage/plugin-app-react';

/**
 * Auth API ref do Keycloak.
 *
 * O Backstage não traz uma auth API ref embutida para OIDC (ao contrário de
 * GitHub/Google), então criamos a nossa. É ela que a página de login
 * referencia para saber *qual* provider usar no botão.
 */
const keycloakAuthApiRef = createApiRef<
    OpenIdConnectApi & ProfileInfoApi & BackstageIdentityApi & SessionApi
>().with({ id: 'auth.keycloak' });

/**
 * Implementação da API: o OAuth2 genérico do Backstage apontado para o
 * provider `oidc` registrado no backend.
 *
 * ⚠️ `provider.id` PRECISA ser exatamente 'oidc' — é o nome que o backend
 * registra. O `title: 'Keycloak'` é apenas o rótulo que aparece na tela.
 */
const keycloakAuthApi = ApiBlueprint.make({
    name: 'keycloak',
    params: defineParams =>
        defineParams({
            api: keycloakAuthApiRef,
            deps: {
                discoveryApi: discoveryApiRef,
                oauthRequestApi: oauthRequestApiRef,
                configApi: configApiRef,
            },
            factory: ({ discoveryApi, oauthRequestApi, configApi }) =>
                OAuth2.create({
                    configApi,
                    discoveryApi,
                    oauthRequestApi,
                    environment: configApi.getOptionalString('auth.environment'),
                    provider: {
                        id: 'oidc',
                        title: 'Keycloak',
                        icon: () => null,
                    },
                    defaultScopes: ['openid', 'profile', 'email'],
                }),
        }),
});

/**
 * Página de login: substitui a padrão por uma com o botão do Keycloak.
 */
const keycloakSignInPage = SignInPageBlueprint.make({
    params: {
        loader: async () => props => (
            <SignInPage
                {...props}
                provider={{
                    id: 'keycloak-auth-provider',
                    title: 'Keycloak',
                    message: 'Entrar com Keycloak',
                    apiRef: keycloakAuthApiRef,
                }}
            />
        ),
    },
});

export const authModule = createFrontendModule({
    pluginId: 'app',
    extensions: [keycloakAuthApi, keycloakSignInPage],
});
