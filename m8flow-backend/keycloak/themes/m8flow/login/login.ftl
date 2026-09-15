<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username','password') displayInfo=realm.password && realm.registrationAllowed && !registrationDisabled??; section>
    <#if section = "header">
        <#assign isM8flowRealmLogin = realm.name == 'm8flow'>
        <#if isM8flowRealmLogin>${msg("loginHeadingShared")}<#else>${msg("loginHeadingMaster")}</#if>
    <#elseif section = "form">
        <#assign isM8flowRealmLogin = realm.name == 'm8flow'>
        <#-- The master realm is a distinct, higher-privilege context reached only
             via the "Platform Admin Sign In" link below (the frontend's old
             two-button realm chooser was replaced by an auto-redirect straight to
             this page — see m8flow-designer/m8flow-frontend TenantSelectPage), so
             it gets its own heading and a subtly different accent color (see
             template.ftl's m8f-org-realm/m8f-admin-realm html class) rather than
             looking identical to the regular shared-realm sign-in. The heading
             text alone ("Platform Admin Sign In") already says which page this
             is, so there's no separate badge repeating it. -->
        <p class="m8f-login-subtitle">
            <#if isM8flowRealmLogin>${msg("loginSubtitleShared")}<#else>${msg("loginSubtitleMaster")}</#if>
        </p>
        <div id="kc-form">
          <div id="kc-form-wrapper">
            <#if usernameHidden??>
                <div
                    id="m8f-hidden-username-login"
                    data-login-restart-url="${url.loginRestartFlowUrl}"
                    hidden
                ></div>
            </#if>
            <#if realm.password>
                <form id="kc-form-login" onsubmit="login.disabled = true; return true;" action="${url.loginAction}" method="post">
                    <#if !usernameHidden??>
                        <div class="${properties.kcFormGroupClass!}">
                            <label for="username" class="${properties.kcLabelClass!}"><#if !realm.loginWithEmailAllowed>${msg("username")}<#elseif !realm.registrationEmailAsUsername>${msg("usernameOrEmail")}<#else>${msg("email")}</#if></label>

                            <input tabindex="2" id="username" class="${properties.kcInputClass!}" name="username" value="${(login.username!'')}"  type="text" autofocus autocomplete="username"
                                   aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>"
                            />

                            <#if messagesPerField.existsError('username','password')>
                                <span id="input-error" class="${properties.kcInputErrorMessageClass!}" aria-live="polite">
                                        ${kcSanitize(messagesPerField.getFirstError('username','password'))?no_esc}
                                </span>
                            </#if>

                        </div>
                    </#if>

                    <div class="${properties.kcFormGroupClass!}">
                        <label for="password" class="${properties.kcLabelClass!}">${msg("password")}</label>

                        <div class="${properties.kcInputGroup!}">
                            <input tabindex="3" id="password" class="${properties.kcInputClass!}" name="password" type="password" autocomplete="current-password"
                                   aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>"
                            />
                            <button class="${properties.kcFormPasswordVisibilityButtonClass!}" type="button" aria-label="${msg("showPassword")}"
                                    aria-controls="password" data-password-toggle tabindex="4"
                                    data-icon-show="${properties.kcFormPasswordVisibilityIconShow!}" data-icon-hide="${properties.kcFormPasswordVisibilityIconHide!}"
                                    data-label-show="${msg('showPassword')}" data-label-hide="${msg('hidePassword')}">
                                <i class="${properties.kcFormPasswordVisibilityIconShow!}" aria-hidden="true"></i>
                            </button>
                        </div>

                        <#if usernameHidden?? && messagesPerField.existsError('username','password')>
                            <span id="input-error" class="${properties.kcInputErrorMessageClass!}" aria-live="polite">
                                    ${kcSanitize(messagesPerField.getFirstError('username','password'))?no_esc}
                            </span>
                        </#if>

                    </div>

                    <div class="${properties.kcFormGroupClass!} ${properties.kcFormSettingClass!}">
                        <div id="kc-form-options">
                            <#if realm.rememberMe && !usernameHidden??>
                                <div class="checkbox">
                                    <label>
                                        <#if login.rememberMe??>
                                            <input tabindex="5" id="rememberMe" name="rememberMe" type="checkbox" checked> ${msg("rememberMe")}
                                        <#else>
                                            <input tabindex="5" id="rememberMe" name="rememberMe" type="checkbox"> ${msg("rememberMe")}
                                        </#if>
                                    </label>
                                </div>
                            </#if>
                            </div>
                            <div class="${properties.kcFormOptionsWrapperClass!}">
                                <#if realm.resetPasswordAllowed>
                                    <span><a tabindex="6" href="${url.loginResetCredentialsUrl}">${msg("doForgotPassword")}</a></span>
                                </#if>
                            </div>

                      </div>

                      <div id="kc-form-buttons" class="${properties.kcFormGroupClass!}">
                          <input type="hidden" id="id-hidden-input" name="credentialId" <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>/>
                          <input tabindex="7" class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}" name="login" id="kc-login" type="submit" value="${msg("doLogIn")}"/>
                      </div>
                      <#if isM8flowRealmLogin>
                          <div class="m8f-realm-switch-hint">
                              <span>${msg("platformAdminHint")}</span>
                              <a
                                  id="m8f-master-login-button"
                                  class="m8f-master-login-link"
                                  data-master-realm-login-button
                                  data-master-realm="master"
                                  data-platform-admin-path="/tenants"
                                  href="#"
                                  aria-disabled="true"
                              >${msg("platformAdminSignIn")}</a>
                          </div>
                      <#else>
                          <div class="m8f-realm-switch-hint">
                              <span>${msg("backToMainHint")}</span>
                              <a
                                  id="m8f-back-to-main-login-button"
                                  class="m8f-back-to-main-login-link"
                                  data-master-realm-login-button
                                  data-master-realm="m8flow"
                                  data-platform-admin-path="/"
                                  href="#"
                                  aria-disabled="true"
                              >${msg("backToMainSignIn")}</a>
                          </div>
                      </#if>
                </form>
            </#if>
            </div>
        </div>
        <script type="module" src="${url.resourcesPath}/js/passwordVisibility.js"></script>
        <script type="module" src="${url.resourcesPath}/js/restartHiddenUsernameLogin.js"></script>
        <script type="module" src="${url.resourcesPath}/js/masterRealmLogin.js"></script>
    <#elseif section = "info" >
        <#if realm.password && realm.registrationAllowed && !registrationDisabled??>
            <div id="kc-registration-container">
                <div id="kc-registration">
                    <span>${msg("noAccount")} <a tabindex="8"
                                                 href="${url.registrationUrl}">${msg("doRegister")}</a></span>
                </div>
            </div>
        </#if>
    <#elseif section = "socialProviders" >
        <#assign isM8flowRealmLogin = realm.name == 'm8flow'>
        <#assign visibleSocialProviders = social.providers![]>
        <#if isM8flowRealmLogin>
            <#-- The "master" IdP is an internal Grafana broker, not the app's
                 platform-admin login. The direct master-realm action above is
                 the supported path and preserves the master token issuer. -->
            <#assign visibleSocialProviders = visibleSocialProviders?filter(provider -> provider.alias != "master")>
        </#if>
        <#if realm.password && visibleSocialProviders?has_content>
            <div id="kc-social-providers" class="${properties.kcFormSocialAccountSectionClass!}">
                <hr/>
                <h2>${msg("identity-provider-login-label")}</h2>
                <ul class="${properties.kcFormSocialAccountListClass!} <#if visibleSocialProviders?size gt 3>${properties.kcFormSocialAccountListGridClass!}</#if>">
                    <#-- Check if numberOfIdps is present -->
                    <#if numberOfIdps??>
                        <#list visibleSocialProviders as sp>
                            <#list identityProviders as idp>
                                <#if sp.alias == idp.alias>
                                <a id="social-${sp.alias}" class="${properties.kcFormSocialAccountListButtonClass!} <#if identityProviders?size gt 3>${properties.kcFormSocialAccountGridItem!}</#if>"
                                    type="button" href="${sp.loginUrl}">
                                    <#if sp.iconClasses?has_content>
                                        <i class="${properties.kcCommonLogoIdP!} ${sp.iconClasses!}" aria-hidden="true"></i>
                                        <span class="${properties.kcFormSocialAccountNameClass!} kc-social-icon-text">${sp.displayName!}</span>
                                    <#else>
                                        <span class="${properties.kcFormSocialAccountNameClass!}">${sp.displayName!}</span>
                                    </#if>
                                </a>
                                </#if>
                            </#list>    
                        </#list>
                    <#else>
                        <#list visibleSocialProviders as p>
                            <li>
                                <a id="social-${p.alias}" class="${properties.kcFormSocialAccountListButtonClass!} <#if visibleSocialProviders?size gt 3>${properties.kcFormSocialAccountGridItem!}</#if>"
                                        type="button" href="${p.loginUrl}">
                                    <#if p.iconClasses?has_content>
                                        <i class="${properties.kcCommonLogoIdP!} ${p.iconClasses!}" aria-hidden="true"></i>
                                        <span class="${properties.kcFormSocialAccountNameClass!} kc-social-icon-text">${p.displayName!}</span>
                                    <#else>
                                        <span class="${properties.kcFormSocialAccountNameClass!}">${p.displayName!}</span>
                                    </#if>
                                 </a>
                            </li>
                        </#list>
                    </#if>
                    
                </ul>
            </div>
        </#if>
    </#if>

</@layout.registrationLayout>
