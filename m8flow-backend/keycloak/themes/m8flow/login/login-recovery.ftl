<#-- Shared by username-only and hidden-username challenges. Recovery runs inline;
     these states never depend on downloading a JavaScript module. -->
<p id="m8f-login-recovery-status" class="instruction" role="status" aria-live="polite">${msg("preparingSignIn")}</p>
<div id="m8f-hidden-username-login-fallback" class="m8f-hidden-username-login-fallback" role="alert" hidden>
    <p class="instruction">${msg("hiddenUsernameLoginFallback")}</p>
    <div class="${properties.kcFormGroupClass!}">
        <a id="m8f-return-to-full-sign-in"
           data-login-restart-url="${url.loginRestartFlowUrl}"
           class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}"
           href="${url.loginRestartFlowUrl}">${msg("returnToFullSignIn")}</a>
    </div>
</div>
<noscript>
    <style>#m8f-login-recovery-status { display: none; }</style>
    <p class="instruction">${msg("hiddenUsernameLoginFallback")}</p>
    <div class="${properties.kcFormGroupClass!}">
        <a id="m8f-return-to-full-sign-in-noscript"
           class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}"
           href="${url.loginRestartFlowUrl}">${msg("returnToFullSignIn")}</a>
    </div>
</noscript>
