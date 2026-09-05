<#escape x as x?html>
<html>
<#include "helpdesk_head_styles.ftl">

<div style="margin:0; padding:24px 12px 8px; background-color:#F4F6F8; font-family:Inter,'Segoe UI',Arial,sans-serif;">

    <table role="presentation"
           width="100%"
           cellspacing="0"
           cellpadding="0"
           border="0"
           style="width:100%; border-collapse:collapse;">
        <tr>
            <td align="center">

                <table role="presentation"
                       width="640"
                       cellspacing="0"
                       cellpadding="0"
                       border="0"
                       style="width:100%; max-width:640px; border-collapse:separate;">

                    <!-- CamCore header -->
                    <tr>
                        <td style="
                            background-color:#101720;
                            padding:30px 36px 26px;
                            border-radius:14px 14px 0 0;
                            text-align:left;
                        ">
                            <img
                                src="https://raw.githubusercontent.com/camcoreau/Seerr/9a457ba35b54999d1f863046c9559d8b90a8e657/public/logo_full.png"
                                width="300"
                                alt="CamCore – Cameron Family Secure Network"
                                style="
                                    display:block;
                                    width:100%;
                                    max-width:300px;
                                    height:auto;
                                    margin:0;
                                    border:0;
                                    outline:none;
                                    text-decoration:none;
                                "
                            >

                            <div style="
                                margin-top:18px;
                                color:#667180;
                                font-size:11px;
                                line-height:16px;
                                font-weight:bold;
                                letter-spacing:1.6px;
                                text-transform:uppercase;
                            ">
                                CamCore Operations &nbsp;&bull;&nbsp; Account Administration
                            </div>
                        </td>
                    </tr>

                    <!-- CamCore coral brand accent -->
                    <tr>
                        <td style="
                            height:5px;
                            line-height:5px;
                            font-size:0;
                            background-color:#FF4B2B;
                        ">
                            &nbsp;
                        </td>
                    </tr>

                    <!-- Main content -->
                    <tr>
                        <td style="
                            background-color:#FFFFFF;
                            padding:38px 36px 34px;
                            border-radius:0 0 14px 14px;
                            color:#101720;
                        ">

                            <div style="
                                display:inline-block;
                                margin:0 0 18px;
                                padding:7px 11px;
                                border:1px solid #FF4B2B;
                                border-radius:20px;
                                background-color:#F4F6F8;
                                color:#C8321A;
                                font-size:11px;
                                line-height:14px;
                                font-weight:bold;
                                letter-spacing:1.2px;
                                text-transform:uppercase;
                            ">
                                Request received
                            </div>

                            <h1 style="
                                margin:0 0 16px;
                                color:#101720;
                                font-size:28px;
                                line-height:35px;
                                font-weight:700;
                            ">
                                Your account administration request is now with CamCore
                            </h1>

                            <p style="
                                margin:0 0 26px;
                                color:#667180;
                                font-size:16px;
                                line-height:25px;
                            ">
                                Thank you for contacting CamCore Account Administration. Your request has been
                                received and added to the account administration queue. CamCore Operations will
                                review the details and respond as soon as possible.
                            </p>

                            <!-- Ticket reference -->
                            <table role="presentation"
                                   width="100%"
                                   cellspacing="0"
                                   cellpadding="0"
                                   border="0"
                                   style="
                                       width:100%;
                                       margin:0 0 26px;
                                       border-collapse:separate;
                                       background-color:#F4F6F8;
                                       border:1px solid #667180;
                                       border-radius:10px;
                                   ">
                                <tr>
                                    <td style="padding:20px 22px;">

                                        <div style="
                                            margin:0 0 6px;
                                            color:#667180;
                                            font-size:11px;
                                            line-height:15px;
                                            font-weight:bold;
                                            letter-spacing:1.3px;
                                            text-transform:uppercase;
                                        ">
                                            Account Administration request reference
                                        </div>

                                        <div style="
                                            margin:0 0 5px;
                                            color:#101720;
                                            font-size:25px;
                                            line-height:31px;
                                            font-weight:bold;
                                        ">
                                            ${issue.id}
                                        </div>

                                        <div style="
                                            color:#667180;
                                            font-size:13px;
                                            line-height:20px;
                                        ">
                                            Keep this reference when contacting CamCore about
                                            your request.
                                        </div>

                                    </td>
                                </tr>
                            </table>

                            <!-- Action button -->
                            <table role="presentation"
                                   cellspacing="0"
                                   cellpadding="0"
                                   border="0"
                                   style="margin:0 0 27px;">
                                <tr>
                                    <td
                                        bgcolor="#C8321A"
                                        style="
                                            border-radius:8px;
                                            text-align:center;
                                        "
                                    >
                                        <a href="${confirmationURL}"
                                           style="
                                               display:inline-block;
                                               padding:14px 24px;
                                               color:#FFFFFF;
                                               font-family:Inter,'Segoe UI',Arial,sans-serif;
                                               font-size:15px;
                                               line-height:19px;
                                               font-weight:bold;
                                               text-decoration:none;
                                               border-radius:8px;
                                           ">
                                            View account administration request
                                        </a>
                                    </td>
                                </tr>
                            </table>

                            <#if commentFromReply>
                                <!-- Reply instructions -->
                                <table role="presentation"
                                       width="100%"
                                       cellspacing="0"
                                       cellpadding="0"
                                       border="0"
                                       style="
                                           width:100%;
                                           margin:0 0 25px;
                                           border-collapse:separate;
                                           background-color:#F4F6F8;
                                           border-left:4px solid #FF4B2B;
                                       ">
                                    <tr>
                                        <td style="
                                            padding:17px 19px;
                                            color:#667180;
                                            font-size:14px;
                                            line-height:22px;
                                        ">
                                            <strong style="color:#101720;">
                                                Need to add more information?
                                            </strong>
                                            <br>
                                            Reply directly to this email and your response will
                                            be added to account administration request ${issue.id}.
                                        </td>
                                    </tr>
                                </table>
                            <#else>
                                <p style="
                                    margin:0 0 25px;
                                    color:#667180;
                                    font-size:14px;
                                    line-height:22px;
                                ">
                                    Use the button above to review or update your request.
                                    Future updates will be delivered to you by email.
                                </p>
                            </#if>

                            <!-- Security notice -->
                            <p style="
                                margin:0 0 28px;
                                color:#667180;
                                font-size:13px;
                                line-height:21px;
                            ">
                                If you did not submit this request, no action is required.
                                You can safely ignore this email.
                            </p>

                            <div style="
                                padding-top:24px;
                                border-top:1px solid #667180;
                            ">
                                <div style="
                                    color:#101720;
                                    font-size:14px;
                                    line-height:21px;
                                    font-weight:bold;
                                ">
                                    CamCore Operations
                                </div>

                                <div style="
                                    margin-top:3px;
                                    color:#667180;
                                    font-size:13px;
                                    line-height:20px;
                                ">
                                    Secure, reliable and professionally managed digital services.
                                </div>
                            </div>

                        </td>
                    </tr>

                </table>

            </td>
        </tr>
    </table>

</div>

<#include "helpdesk_footer.ftl">
</html>
</#escape>
