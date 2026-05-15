package com.m8flow.keycloak.mapper;

import org.keycloak.models.ClientSessionContext;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.ProtocolMapperModel;
import org.keycloak.models.UserSessionModel;
import org.keycloak.models.utils.KeycloakModelUtils;
import org.keycloak.protocol.oidc.mappers.AbstractOIDCProtocolMapper;
import org.keycloak.protocol.oidc.mappers.OIDCAccessTokenMapper;
import org.keycloak.protocol.oidc.mappers.OIDCAttributeMapperHelper;
import org.keycloak.protocol.oidc.mappers.OIDCIDTokenMapper;
import org.keycloak.protocol.oidc.mappers.TokenIntrospectionTokenMapper;
import org.keycloak.protocol.oidc.mappers.UserInfoTokenMapper;
import org.keycloak.provider.ProviderConfigProperty;
import org.keycloak.representations.IDToken;

import java.util.ArrayList;
import java.util.List;

public class NormalizedGroupMembershipMapper extends AbstractOIDCProtocolMapper
    implements OIDCAccessTokenMapper, OIDCIDTokenMapper, UserInfoTokenMapper, TokenIntrospectionTokenMapper {

    public static final String PROVIDER_ID = "oidc-normalized-group-membership-mapper";

    private static final List<ProviderConfigProperty> CONFIG_PROPERTIES = new ArrayList<>();

    static {
        OIDCAttributeMapperHelper.addTokenClaimNameConfig(CONFIG_PROPERTIES);
        OIDCAttributeMapperHelper.addIncludeInTokensConfig(CONFIG_PROPERTIES, NormalizedGroupMembershipMapper.class);
    }

    @Override
    public String getDisplayCategory() {
        return TOKEN_MAPPER_CATEGORY;
    }

    @Override
    public String getDisplayType() {
        return "Normalized Group Membership Mapper";
    }

    @Override
    public String getHelpText() {
        return "Adds group membership paths to the token after removing any leading slash characters.";
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
    protected void setClaim(
        IDToken token,
        ProtocolMapperModel mappingModel,
        UserSessionModel userSession,
        KeycloakSession keycloakSession,
        ClientSessionContext clientSessionCtx
    ) {
        String claimName = mappingModel.getConfig().get(OIDCAttributeMapperHelper.TOKEN_CLAIM_NAME);
        if (claimName == null || claimName.isBlank()) {
            claimName = "groups";
        }

        List<String> normalizedGroups = userSession.getUser().getGroupsStream()
            .map(KeycloakModelUtils::buildGroupPath)
            .filter(path -> path != null && !path.isBlank())
            .map(NormalizedGroupMembershipMapper::stripLeadingSlashes)
            .distinct()
            .toList();

        token.getOtherClaims().put(claimName, normalizedGroups);
    }

    private static String stripLeadingSlashes(String groupPath) {
        return groupPath.replaceFirst("^/+", "");
    }
}
