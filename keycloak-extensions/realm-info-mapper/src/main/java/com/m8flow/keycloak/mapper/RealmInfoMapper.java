package com.m8flow.keycloak.mapper;

import org.keycloak.models.ClientSessionContext;
import org.keycloak.models.OrganizationModel;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.ProtocolMapperModel;
import org.keycloak.models.RealmModel;
import org.keycloak.models.UserSessionModel;
import org.keycloak.organization.utils.Organizations;
import org.keycloak.protocol.oidc.mappers.AbstractOIDCProtocolMapper;
import org.keycloak.protocol.oidc.mappers.OIDCAccessTokenMapper;
import org.keycloak.protocol.oidc.mappers.OIDCIDTokenMapper;
import org.keycloak.protocol.oidc.mappers.OIDCAttributeMapperHelper;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.representations.IDToken;

import java.util.ArrayList;
import java.util.List;

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
    }

    private static OrganizationModel resolveOrganization(UserSessionModel userSession, KeycloakSession keycloakSession) {
        if (userSession == null || userSession.getUser() == null) {
            return null;
        }
        return Organizations.resolveOrganization(keycloakSession, userSession.getUser());
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
