package com.m8flow.keycloak.mapper;

import org.keycloak.models.ClientSessionContext;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.ProtocolMapperModel;
import org.keycloak.models.UserSessionModel;
import org.keycloak.protocol.oidc.mappers.AbstractOIDCProtocolMapper;
import org.keycloak.protocol.oidc.mappers.OIDCAccessTokenMapper;
import org.keycloak.protocol.oidc.mappers.OIDCAttributeMapperHelper;
import org.keycloak.protocol.oidc.mappers.OIDCIDTokenMapper;
import org.keycloak.protocol.oidc.mappers.TokenIntrospectionTokenMapper;
import org.keycloak.protocol.oidc.mappers.UserInfoTokenMapper;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.representations.IDToken;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class NormalizedOrganizationMembershipMapper extends AbstractOIDCProtocolMapper
    implements OIDCAccessTokenMapper, OIDCIDTokenMapper, UserInfoTokenMapper, TokenIntrospectionTokenMapper {

    public static final String PROVIDER_ID = "oidc-normalized-organization-membership-mapper";

    private static final List<ProviderConfigProperty> CONFIG_PROPERTIES = new ArrayList<>();

    static {
        OIDCAttributeMapperHelper.addTokenClaimNameConfig(CONFIG_PROPERTIES);
        OIDCAttributeMapperHelper.addIncludeInTokensConfig(CONFIG_PROPERTIES, NormalizedOrganizationMembershipMapper.class);
    }

    @Override
    public String getDisplayCategory() {
        return TOKEN_MAPPER_CATEGORY;
    }

    @Override
    public String getDisplayType() {
        return "Normalized Organization Membership Mapper";
    }

    @Override
    public String getHelpText() {
        return "Normalizes organization claim group entries by removing any leading slash characters.";
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
    public int getPriority() {
        return 1000;
    }

    @Override
    protected void setClaim(
        IDToken token,
        ProtocolMapperModel mappingModel,
        UserSessionModel userSession,
        KeycloakSession keycloakSession,
        ClientSessionContext clientSessionCtx
    ) {
        String claimName = mappingModel.getConfig().get(OIDCAttributeMapperHelper.TOKEN_CLAIM_NAME);
        if (claimName == null || claimName.isBlank()) {
            claimName = "organization";
        }

        Object existingClaim = token.getOtherClaims().get(claimName);
        if (existingClaim == null) {
            return;
        }

        token.getOtherClaims().put(claimName, normalizeOrganizationClaim(existingClaim, false));
    }

    private static Object normalizeOrganizationClaim(Object value, boolean normalizeGroupMembers) {
        if (value instanceof Map<?, ?> mapValue) {
            Map<String, Object> normalizedMap = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : mapValue.entrySet()) {
                String key = String.valueOf(entry.getKey());
                normalizedMap.put(key, normalizeOrganizationClaim(entry.getValue(), "groups".equals(key)));
            }
            return normalizedMap;
        }

        if (value instanceof List<?> listValue) {
            List<Object> normalizedList = new ArrayList<>(listValue.size());
            for (Object listEntry : listValue) {
                if (normalizeGroupMembers && listEntry instanceof String stringEntry) {
                    normalizedList.add(stripLeadingSlashes(stringEntry));
                } else {
                    normalizedList.add(normalizeOrganizationClaim(listEntry, false));
                }
            }
            return normalizedList;
        }

        return value;
    }

    private static String stripLeadingSlashes(String value) {
        return value.replaceFirst("^/+", "");
    }
}
