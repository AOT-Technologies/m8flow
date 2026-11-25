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
                <#include "login-recovery.ftl">
            </div>
        </div>
        <script><#include "resources/js/restartHiddenUsernameLogin.js" parse=false></script>
    </#if>
</@layout.registrationLayout>
