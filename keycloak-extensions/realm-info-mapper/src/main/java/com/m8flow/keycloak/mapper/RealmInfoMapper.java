package com.m8flow.keycloak.mapper;

import org.keycloak.models.ClientSessionContext;
import org.keycloak.models.OrganizationModel;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.ProtocolMapperModel;
import org.keycloak.models.RealmModel;
import org.keycloak.models.UserModel;
import org.keycloak.models.UserSessionModel;
import org.keycloak.organization.OrganizationProvider;
import org.keycloak.organization.utils.Organizations;
import org.keycloak.protocol.oidc.mappers.AbstractOIDCProtocolMapper;
import org.keycloak.protocol.oidc.mappers.OIDCAccessTokenMapper;
import org.keycloak.protocol.oidc.mappers.OIDCIDTokenMapper;
import org.keycloak.protocol.oidc.mappers.OIDCAttributeMapperHelper;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.representations.IDToken;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class RealmInfoMapper extends AbstractOIDCProtocolMapper implements OIDCAccessTokenMapper, OIDCIDTokenMapper {

    public static final String PROVIDER_ID = "oidc-realm-info-mapper";

    private static final List<ProviderConfigProperty> CONFIG_PROPERTIES = new ArrayList<>();

    static {
        OIDCAttributeMapperHelper.addIncludeInTokensConfig(CONFIG_PROPERTIES, RealmInfoMapper.class);
    }

    @Override
    public String getDisplayCategory() {
        return TOKEN_MAPPER_CATEGORY;
    }

    @Override
    public String getDisplayType() {
        return "Realm Info Mapper";
    }

    @Override
    public String getHelpText() {
        return "Adds explicit realm/auth claims and active-organization tenant claims to the token.";
    }

    @Override
    public List<ProviderConfigProperty> getConfigProperties() {
        return CONFIG_PROPERTIES;
    }

    @Override
    public String getId() {
        return PROVIDER_ID;
    }

    /**
     * User attribute the backend writes (via Admin API) to name the single
     * active organization for this user — the switch-tenant flow's signal
     * (active-tenant deep-module map, ticket 08/09/10). Holds the org id.
     * A refresh_token grant re-runs this mapper and reads the fresh value
     * (verified: KC re-mints on refresh with the freshly-written attribute).
     */
    public static final String ACTIVE_TENANT_ATTRIBUTE = "m8flow_active_tenant";

    @Override
    protected void setClaim(IDToken token, ProtocolMapperModel mappingModel,
                          UserSessionModel userSession, KeycloakSession keycloakSession,
                          ClientSessionContext clientSessionCtx) {
        RealmModel realm = keycloakSession.getContext().getRealm();
        putIfNotBlank(token, "m8flow_authentication_identifier", realm.getName());
        putIfNotBlank(token, "m8flow_realm_name", realm.getName());
        putIfNotBlank(token, "m8flow_realm_id", realm.getId());

        OrganizationModel organization = resolveOrganization(userSession, keycloakSession);
        if (organization == null) {
            return;
        }

        putIfNotBlank(token, "m8flow_tenant_id", organization.getId());
        putIfNotBlank(token, "m8flow_tenant_alias", organization.getAlias());
        putIfNotBlank(token, "m8flow_tenant_name", organization.getName() != null ? organization.getName() : organization.getAlias());

        // Populate the single-active-org `organization` claim ourselves. The
        // stock org-membership mapper leaves this empty for a multi-org user
        // with no org-scope selection (KC26 limitation, see ticket 08), and the
        // org's group memberships are not reachable from the protocol-mapper
        // SPI — the backend derives roles from the Keycloak Admin API directory,
        // not this claim (sync_groups_from_token reads VerifiedClaims enriched
        // from the directory, not the raw token). So we emit id + name here;
        // any `groups` sub-entry stays the province of the stock
        // organization-group mapper when an active-org context exists.
        String alias = organization.getAlias();
        if (alias != null && !alias.isBlank()) {
            Map<String, Object> orgDetails = new LinkedHashMap<>();
            if (organization.getId() != null) {
                orgDetails.put("id", organization.getId());
            }
            String orgName = organization.getName() != null ? organization.getName() : organization.getAlias();
            if (orgName != null && !orgName.isBlank()) {
                orgDetails.put("name", orgName);
            }
            Map<String, Object> orgClaim = new LinkedHashMap<>();
            orgClaim.put(alias.trim(), orgDetails);
            token.getOtherClaims().put("organization", orgClaim);
        }
    }

    /**
     * Prefer the backend-set active-tenant attribute (single active org per
     * user, cookie-authoritative — ticket 08); fall back to Keycloak's own
     * resolution for a genuine single-org user / pre-first-switch login.
     *
     * The attribute normally holds the org id (what the backend writes), but a
     * bare org alias is accepted too (ticket 09). Either way the result is gated
     * on membership so a stale/forged attribute can never mint a token for an
     * org the user does not belong to.
     */
    private static OrganizationModel resolveOrganization(UserSessionModel userSession, KeycloakSession keycloakSession) {
        if (userSession == null || userSession.getUser() == null) {
            return null;
        }
        UserModel user = userSession.getUser();

        String activeTenant = user.getFirstAttribute(ACTIVE_TENANT_ATTRIBUTE);
        if (activeTenant != null && !activeTenant.isBlank()) {
            OrganizationProvider organizations = keycloakSession.getProvider(OrganizationProvider.class);
            if (organizations != null) {
                String key = activeTenant.trim();
                OrganizationModel byId = organizations.getById(key);
                if (byId != null && organizations.isMember(byId, user)) {
                    return byId;
                }
                // Not an id (or not a membership) -- OrganizationProvider has no
                // getByAlias, so match the alias against the user's own orgs,
                // which also enforces membership by construction.
                OrganizationModel byAlias = organizations.getByMember(user)
                    .filter(org -> key.equals(org.getAlias()) || key.equals(org.getId()))
                    .findFirst()
                    .orElse(null);
                if (byAlias != null) {
                    return byAlias;
                }
            }
        }

        return Organizations.resolveOrganization(keycloakSession, user);
    }

    private static void putIfNotBlank(IDToken token, String claimName, String value) {
        if (value == null) {
            return;
        }

        String normalized = value.trim();
        if (normalized.isEmpty()) {
            return;
        }

        token.getOtherClaims().put(claimName, normalized);
    }
}
