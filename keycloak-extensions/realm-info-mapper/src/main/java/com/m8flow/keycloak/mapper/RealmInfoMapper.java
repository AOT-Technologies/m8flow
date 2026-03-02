package com.m8flow.keycloak.mapper;

import org.keycloak.models.ClientSessionContext;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.ProtocolMapperModel;
import org.keycloak.models.RealmModel;
import org.keycloak.models.UserSessionModel;
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
        return "Adds m8flow_tenant_id and m8flow_tenant_name to the token claims.";
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

        // This dynamically fetches the current realm's name and ID (m8flow claim names)
        RealmModel realm = keycloakSession.getContext().getRealm();

        token.getOtherClaims().put("m8flow_tenant_name", realm.getName());
        token.getOtherClaims().put("m8flow_tenant_id", realm.getId());
    }
}
