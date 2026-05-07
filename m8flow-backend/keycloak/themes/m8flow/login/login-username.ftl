<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=false displayInfo=false; section>
    <#if section = "header">
        ${msg("loginAccountTitle")}
    <#elseif section = "form">
        <div id="kc-form">
            <div id="kc-form-wrapper">
                <div
                    id="m8f-username-only-login"
                    data-login-restart-url="${url.loginRestartFlowUrl}"
                    hidden
                ></div>
                <noscript>
                    <div class="${properties.kcFormGroupClass!}">
                        <a
                            class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}"
                            href="${url.loginRestartFlowUrl}"
                        >${msg("returnToFullSignIn")}</a>
                    </div>
                </noscript>
            </div>
        </div>
        <script type="module" src="${url.resourcesPath}/js/restartHiddenUsernameLogin.js"></script>
    </#if>
</@layout.registrationLayout>
