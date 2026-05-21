package com.m8flow.keycloak.mapper;

import org.keycloak.models.ClientSessionContext;
import org.keycloak.models.OrganizationModel;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.ProtocolMapperModel;
import org.keycloak.models.UserSessionModel;
import org.keycloak.models.utils.KeycloakModelUtils;
import org.keycloak.organization.utils.Organizations;
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

        Object normalizedClaim = normalizeOrganizationClaim(existingClaim, false);
        OrganizationModel activeOrganization = resolveOrganization(userSession, keycloakSession);
        if (activeOrganization != null) {
            normalizedClaim = injectNormalizedGroups(
                normalizedClaim,
                activeOrganization,
                normalizedUserGroupPaths(userSession)
            );
        }

        token.getOtherClaims().put(claimName, normalizedClaim);
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

    private static Object injectNormalizedGroups(
        Object existingClaim,
        OrganizationModel activeOrganization,
        List<String> normalizedGroups
    ) {
        if (!(existingClaim instanceof Map<?, ?> existingClaimMap)) {
            return existingClaim;
        }

        Map<String, Object> updatedClaim = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : existingClaimMap.entrySet()) {
            String key = String.valueOf(entry.getKey());
            Object value = entry.getValue();

            if (value instanceof Map<?, ?> organizationDetails && organizationEntryMatches(key, organizationDetails, activeOrganization)) {
                Map<String, Object> updatedOrganizationDetails = new LinkedHashMap<>();
                for (Map.Entry<?, ?> detailEntry : organizationDetails.entrySet()) {
                    updatedOrganizationDetails.put(String.valueOf(detailEntry.getKey()), detailEntry.getValue());
                }
                updatedOrganizationDetails.put("groups", normalizedGroups);
                updatedClaim.put(key, updatedOrganizationDetails);
                continue;
            }

            updatedClaim.put(key, value);
        }

        return updatedClaim;
    }

    private static boolean organizationEntryMatches(
        String claimKey,
        Map<?, ?> organizationDetails,
        OrganizationModel activeOrganization
    ) {
        String alias = activeOrganization.getAlias();
        if (alias != null && alias.equals(claimKey)) {
            return true;
        }

        Object organizationId = organizationDetails.get("id");
        return organizationId instanceof String && activeOrganization.getId().equals(organizationId);
    }

    private static List<String> normalizedUserGroupPaths(UserSessionModel userSession) {
        if (userSession == null || userSession.getUser() == null) {
            return List.of();
        }

        return userSession.getUser().getGroupsStream()
            .map(KeycloakModelUtils::buildGroupPath)
            .filter(path -> path != null && !path.isBlank())
            .map(NormalizedOrganizationMembershipMapper::stripLeadingSlashes)
            .distinct()
            .toList();
    }

    private static OrganizationModel resolveOrganization(UserSessionModel userSession, KeycloakSession keycloakSession) {
        if (userSession == null || userSession.getUser() == null) {
            return null;
        }

        return Organizations.resolveOrganization(keycloakSession, userSession.getUser());
    }

    private static String stripLeadingSlashes(String value) {
        return value.replaceFirst("^/+", "");
    }
}
