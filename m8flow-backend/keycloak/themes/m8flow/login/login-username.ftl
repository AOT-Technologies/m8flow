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
                    data-login-restart-fallback-id="m8f-hidden-username-login-fallback"
                    hidden
                ></div>
                <div
                    id="m8f-hidden-username-login-fallback"
                    class="m8f-hidden-username-login-fallback"
                    hidden
                >
                    <p class="instruction">${msg("hiddenUsernameLoginFallback")}</p>
                    <div class="${properties.kcFormGroupClass!}">
                        <a
                            id="m8f-return-to-full-sign-in"
                            data-login-restart-url="${url.loginRestartFlowUrl}"
                            class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}"
                            href="${url.loginRestartFlowUrl}"
                        >${msg("returnToFullSignIn")}</a>
                    </div>
                </div>
                <noscript>
                    <div class="${properties.kcFormGroupClass!}">
                        <a
                            id="m8f-return-to-full-sign-in-noscript"
                            class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}"
                            href="${url.loginRestartFlowUrl}"
                        >${msg("returnToFullSignIn")}</a>
                    </div>
                </noscript>
            </div>
        </div>
        <script type="module" src="${url.resourcesPath}/js/restartHiddenUsernameLogin.js"></script>
        <script>
            // Classic script: runs even when the ES module above is blocked or fails to
            // load. The module normally navigates away via location.replace() long before
            // this fires; if it never ran, surface the manual restart link rather than
            // leaving an empty form. The <noscript> block only covers JS being disabled.
            setTimeout(function () {
                var fallback = document.getElementById('m8f-hidden-username-login-fallback');
                if (fallback) {
                    fallback.hidden = false;
                }
            }, 5000);
        </script>
    </#if>
</@layout.registrationLayout>
