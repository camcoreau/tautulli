<#-- Formatting only: this marker is not an authorization boundary. -->
<#assign camcoreOnboarding = false>
<#if (issue.id)?? && issue.id?is_string
    && (issue.summary)?? && issue.summary?is_string
    && (issue.description)?? && issue.description?is_string>
    <#assign camcoreOnboarding = issue.id?matches("CMA-[1-9][0-9]*")
        && issue.summary == "Welcome to Cameron-Media — Your access is ready"
        && issue.description?replace("\r\n", "\n")?starts_with("<!-- CamCore:CMA:onboarding:v1 -->\n\n## Welcome to Cameron-Media\n")>
</#if>
