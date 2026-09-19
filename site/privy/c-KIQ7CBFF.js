import{a as Y}from"./c-NDC5DROA.js";import{a as X}from"./c-RUR3CLUG.js";import{a as Q}from"./c-TABTNE5T.js";import{c as Z}from"./c-LZ25EMVC.js";import{a as H}from"./c-HTRSEHP5.js";import{a as z}from"./c-FYLEYBR7.js";import"./c-MB24CLN6.js";import"./c-G7QKMXDE.js";import"./c-EOAJVKNP.js";import"./c-TUUPII4V.js";import"./c-TFXIZIPD.js";import"./c-3RWNX7T6.js";import"./c-4I3SX4H3.js";import"./c-4BLT7WQF.js";import"./c-ZHAQSROJ.js";import"./c-CI4Y2PA4.js";import"./c-BDOXXWKK.js";import{a as ie}from"./c-TY233LCP.js";import"./c-5BKC3C2P.js";import"./c-HT5VPXS6.js";import"./c-4CVEF6WY.js";import"./c-BLX4OB5V.js";import"./c-35MSG53D.js";import"./c-TCALT4TQ.js";import"./c-R2JM2JIB.js";import"./c-IR2Q2AZQ.js";import"./c-RROTPPQ4.js";import"./c-2Z7ML7DV.js";import"./c-TEZKH2R4.js";import"./c-3ZJETHS3.js";import{b as f,h as v,l as V}from"./c-TK45UUBT.js";import"./c-5AQXWU74.js";import"./c-FKNR4ZMH.js";import{b as K}from"./c-65SYQ2BY.js";import{b as g}from"./c-LC7NBPXT.js";import{Ab as q,Ca as B,Sa as U,wb as P}from"./c-Z3FRICV3.js";import"./c-FYFAMDSG.js";import{a as $,b as te}from"./c-3POUIAFT.js";import"./c-K6YWNVGO.js";import"./c-K4BTFUAC.js";import"./c-DBE6YW6D.js";import"./c-F3P6SX6T.js";import"./c-4ERX45K7.js";import{e as k}from"./c-7SW4JVF5.js";var r=k(te(),1);var w=k($(),1);function ae({title:o,titleId:d,...C},p){return w.createElement("svg",Object.assign({xmlns:"http://www.w3.org/2000/svg",viewBox:"0 0 20 20",fill:"currentColor","aria-hidden":"true","data-slot":"icon",ref:p,"aria-labelledby":d},C),o?w.createElement("title",{id:d},o):null,w.createElement("path",{fillRule:"evenodd",d:"M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z",clipRule:"evenodd"}))}var ne=w.forwardRef(ae),G=ne;var s=k($(),1),oe=k(ie(),1);var se=({contactMethod:o,authFlow:d,emailDomain:C,appName:p="Privy",whatsAppEnabled:I=!1,onBack:E,onCodeSubmit:M,onResend:L,errorMessage:m,success:h=!1,resendCountdown:D=0,onInvalidInput:O,onClearError:N})=>{let[c,S]=(0,s.useState)(ee);(0,s.useEffect)((()=>{m||S(ee)}),[m]);let x=async y=>{y.preventDefault();let t=y.currentTarget.value.replace(" ","");if(t==="")return;if(isNaN(Number(t)))return void O?.("Code should be numeric");N?.();let u=Number(y.currentTarget.name?.charAt(5)),a=[...t||[""]].slice(0,J-u),n=[...c.slice(0,u),...a,...c.slice(u+a.length)];S(n);let b=Math.min(Math.max(u+a.length,0),J-1);isNaN(Number(y.currentTarget.value))||document.querySelector(`input[name=code-${b}]`)?.focus(),n.every((l=>l&&!isNaN(+l)))&&(document.querySelector(`input[name=code-${b}]`)?.blur(),await M?.(n.join("")))};return(0,r.jsx)(z,{title:"Enter confirmation code",subtitle:(0,r.jsxs)("span",d==="email"?{children:["Please check ",(0,r.jsx)(re,{children:o})," for an email from"," ",C??"privy.io"," and enter your code below."]}:{children:["Please check ",(0,r.jsx)(re,{children:o})," for a",I?" WhatsApp":""," message from ",p," and enter your code below."]}),icon:d==="email"?X:Y,onBack:E,showBack:!0,helpText:(0,r.jsxs)(ue,{children:[(0,r.jsxs)("span",{children:["Didn't get ",d==="email"?"an email":"a message","?"]}),D?(0,r.jsxs)(fe,{children:[(0,r.jsx)(G,{color:"var(--privy-color-foreground)",strokeWidth:1.33,height:"12px",width:"12px"}),(0,r.jsx)("span",{children:"Code sent"})]}):(0,r.jsx)(Q,{as:"button",size:"sm",onClick:L,children:"Resend code"})]}),children:(0,r.jsx)(de,{children:(0,r.jsx)(Z,{children:(0,r.jsxs)(pe,{children:[(0,r.jsx)("div",{children:c.map(((y,t)=>(0,r.jsx)("input",{name:`code-${t}`,type:"text",value:c[t],onChange:x,onKeyUp:u=>{u.key==="Backspace"&&(a=>{N?.(),S([...c.slice(0,a),"",...c.slice(a+1)]),a>0&&document.querySelector(`input[name=code-${a-1}]`)?.focus()})(t)},inputMode:"numeric",autoFocus:t===0,pattern:"[0-9]",className:`${h?"success":""} ${m?"fail":""}`,autoComplete:oe.isMobile?"one-time-code":"off"},t)))}),(0,r.jsx)(me,{$fail:!!m,$success:h,children:(0,r.jsx)("span",{children:m==="Invalid or expired verification code"?"Incorrect code":m||(h?"Success!":"")})})]})})})})},J=6,ee=Array(6).fill(""),A,T,le=((A=le||{})[A.RESET_AFTER_DELAY=0]="RESET_AFTER_DELAY",A[A.CLEAR_ON_NEXT_VALID_INPUT=1]="CLEAR_ON_NEXT_VALID_INPUT",A),ce=((T=ce||{})[T.EMAIL=0]="EMAIL",T[T.SMS=1]="SMS",T),Ie={component:()=>{let{navigate:o,lastScreen:d,navigateBack:C,setModalData:p,onUserCloseViaDialogOrKeybindRef:I}=K(),E=P(),{closePrivyModal:M,resendEmailCode:L,resendSmsCode:m,getAuthMeta:h,loginWithCode:D,updateWallets:O,createAnalyticsEvent:N}=B(),{authenticated:c,logout:S,user:x}=q(),{whatsAppEnabled:y}=P(),[t,u]=(0,s.useState)(!1),[a,n]=(0,s.useState)(null),[b,l]=(0,s.useState)(null),[_,j]=(0,s.useState)(0);I.current=()=>null;let R=h()?.email?0:1,F=R===0?h()?.email||"":h()?.phoneNumber||"",W=U-500;return(0,s.useEffect)((()=>{if(_){let i=setTimeout((()=>{j(_-1)}),1e3);return()=>clearTimeout(i)}}),[_]),(0,s.useEffect)((()=>{if(c&&t&&x){if(E?.legal.requireUsersAcceptTerms&&!x.hasAcceptedTerms){let i=setTimeout((()=>{o("AffirmativeConsentScreen")}),W);return()=>clearTimeout(i)}if(H(x,E.embeddedWallets)){let i=setTimeout((()=>{p({createWallet:{onSuccess:()=>{},onFailure:e=>{console.error(e),N({eventName:"embedded_wallet_creation_failure_logout",payload:{error:e,screen:"AwaitingPasswordlessCodeScreen"}}),S()},callAuthOnSuccessOnClose:!0}}),o("EmbeddedWalletOnAccountCreateScreen")}),W);return()=>clearTimeout(i)}{O();let i=setTimeout((()=>M({shouldCallAuthOnSuccess:!0,isSuccess:!0})),U);return()=>clearTimeout(i)}}}),[c,t,x]),(0,s.useEffect)((()=>{if(a&&b===0){let i=setTimeout((()=>{n(null),l(null),document.querySelector("input[name=code-0]")?.focus()}),1400);return()=>clearTimeout(i)}}),[a,b]),(0,r.jsx)(se,{contactMethod:F,authFlow:R===0?"email":"sms",emailDomain:E?.appearance.emailDomain,appName:E?.name,whatsAppEnabled:y,onBack:()=>C(),onCodeSubmit:async i=>{try{await D(i),u(!0)}catch(e){if(e instanceof f&&e.privyErrorCode===v.INVALID_CREDENTIALS)n("Invalid or expired verification code"),l(0);else if(e instanceof f&&e.privyErrorCode===v.CANNOT_LINK_MORE_OF_TYPE)n(e.message);else{if(e instanceof f&&e.privyErrorCode===v.USER_LIMIT_REACHED)return console.error(new V(e).toString()),void o("UserLimitReachedScreen");if(e instanceof f&&e.privyErrorCode===v.USER_DOES_NOT_EXIST)return void o("AccountNotFoundScreen");if(e instanceof f&&e.privyErrorCode===v.LINKED_TO_ANOTHER_USER)return p({errorModalData:{error:e,previousScreen:d??"AwaitingPasswordlessCodeScreen"}}),void o("ErrorScreen",!1);if(e instanceof f&&e.privyErrorCode===v.DISALLOWED_PLUS_EMAIL)return p({inlineError:{error:e}}),void o("ConnectOrCreateScreen",!1);if(e instanceof f&&e.privyErrorCode===v.ACCOUNT_TRANSFER_REQUIRED&&e.data?.data?.nonce)return p({accountTransfer:{nonce:e.data?.data?.nonce,account:F,displayName:e.data?.data?.account?.displayName,linkMethod:R===0?"email":"sms",embeddedWalletAddress:e.data?.data?.otherUser?.embeddedWalletAddress}}),void o("LinkConflictScreen");n("Issue verifying code"),l(0)}}},onResend:async()=>{j(30),R===0?await L():await m()},errorMessage:a||void 0,success:t,resendCountdown:_,onInvalidInput:i=>{n(i),l(1)},onClearError:()=>{b===1&&(n(null),l(null))}})}},de=g.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  margin: auto;
  gap: 16px;
  flex-grow: 1;
  width: 100%;
`,pe=g.div`
  display: flex;
  flex-direction: column;
  width: 100%;
  gap: 12px;

  > div:first-child {
    display: flex;
    justify-content: center;
    gap: 0.5rem;
    width: 100%;
    border-radius: var(--privy-border-radius-sm);

    > input {
      border: 1px solid var(--privy-color-foreground-4);
      background: var(--privy-color-background);
      border-radius: var(--privy-border-radius-sm);
      padding: 8px 10px;
      height: 48px;
      width: 40px;
      text-align: center;
      font-size: 18px;
      font-weight: 600;
      color: var(--privy-color-foreground);
      transition: all 0.2s ease;
    }

    > input:focus {
      border: 1px solid var(--privy-color-foreground);
      box-shadow: 0 0 0 1px var(--privy-color-foreground);
    }

    > input:invalid {
      border: 1px solid var(--privy-color-error);
    }

    > input.success {
      border: 1px solid var(--privy-color-border-success);
      background: var(--privy-color-success-bg);
    }

    > input.fail {
      border: 1px solid var(--privy-color-border-error);
      background: var(--privy-color-error-bg);
      animation: shake 180ms;
      animation-iteration-count: 2;
    }
  }

  @keyframes shake {
    0% {
      transform: translate(1px, 0);
    }
    33% {
      transform: translate(-1px, 0);
    }
    67% {
      transform: translate(-1px, 0);
    }
    100% {
      transform: translate(1px, 0);
    }
  }
`,me=g.div`
  line-height: 20px;
  min-height: 20px;
  font-size: 14px;
  font-weight: 400;
  color: ${o=>o.$success?"var(--privy-color-success-dark)":o.$fail?"var(--privy-color-error-dark)":"transparent"};
  display: flex;
  justify-content: center;
  width: 100%;
  text-align: center;
`,ue=g.div`
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  width: 100%;
  color: var(--privy-color-foreground-2);
`,fe=g.div`
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--privy-border-radius-sm);
  padding: 2px 8px;
  gap: 4px;
  background: var(--privy-color-background-2);
  color: var(--privy-color-foreground-2);
`,re=g.span`
  font-weight: 500;
  word-break: break-all;
  color: var(--privy-color-foreground);
`;export{Ie as AwaitingPasswordlessCodeScreen,se as AwaitingPasswordlessCodeScreenView,Ie as default};
