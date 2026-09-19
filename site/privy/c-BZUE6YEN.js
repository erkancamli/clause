import{a as P}from"./c-CLWF3UXN.js";import{a as E}from"./c-Q4WEUERI.js";import{a as V}from"./c-FE7DUGCR.js";import{a as ee,b as Q}from"./c-CUILO6RP.js";import{a as q}from"./c-HTRSEHP5.js";import{a as B}from"./c-FYLEYBR7.js";import"./c-MB24CLN6.js";import{d as z,n as W}from"./c-F2M6QL3Y.js";import"./c-G7QKMXDE.js";import{f as j}from"./c-EOAJVKNP.js";import"./c-YDIUEEIG.js";import"./c-TUUPII4V.js";import"./c-TFXIZIPD.js";import"./c-3RWNX7T6.js";import"./c-4I3SX4H3.js";import"./c-4BLT7WQF.js";import"./c-ZHAQSROJ.js";import"./c-CI4Y2PA4.js";import"./c-BDOXXWKK.js";import{a as Z}from"./c-TY233LCP.js";import"./c-5BKC3C2P.js";import"./c-HT5VPXS6.js";import"./c-4CVEF6WY.js";import"./c-BLX4OB5V.js";import"./c-35MSG53D.js";import"./c-TCALT4TQ.js";import"./c-R2JM2JIB.js";import"./c-IR2Q2AZQ.js";import"./c-RROTPPQ4.js";import"./c-2Z7ML7DV.js";import"./c-TEZKH2R4.js";import"./c-3ZJETHS3.js";import{h as l,l as $}from"./c-TK45UUBT.js";import"./c-5AQXWU74.js";import"./c-FKNR4ZMH.js";import{b as D}from"./c-65SYQ2BY.js";import{b as a,f as M}from"./c-LC7NBPXT.js";import{Ab as U,Ca as I,Sa as x,wb as N}from"./c-Z3FRICV3.js";import"./c-FYFAMDSG.js";import{a as Y,b as G}from"./c-3POUIAFT.js";import"./c-K6YWNVGO.js";import"./c-K4BTFUAC.js";import"./c-DBE6YW6D.js";import"./c-F3P6SX6T.js";import"./c-4ERX45K7.js";import{e as C}from"./c-7SW4JVF5.js";var e=C(G(),1),s=C(Y(),1),y=C(Z(),1);var Oe=C(ee(),1);var re=a.div`
  width: 100%;
`,te=a.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.75rem;
  height: 56px;
  background: ${r=>r.$disabled?"var(--privy-color-background-2)":"var(--privy-color-background)"};
  border: 1px solid var(--privy-color-foreground-4);
  border-radius: var(--privy-border-radius-md);

  &:hover {
    border-color: ${r=>r.$disabled?"var(--privy-color-foreground-4)":"var(--privy-color-foreground-3)"};
  }
`,ie=a.div`
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
`,H=a.span`
  display: block;
  font-size: 16px;
  line-height: 24px;
  color: ${r=>r.$disabled?"var(--privy-color-foreground-2)":"var(--privy-color-foreground)"};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  /* Single-line truncation: as a flex item this would otherwise be floored at its
     min-content width, so min-width: 0 lets it shrink and the ellipsis land at the
     container edge. */
  min-width: 0;

  @media (min-width: 441px) {
    font-size: 14px;
    line-height: 20px;
  }
`,oe=a(H)`
  color: var(--privy-color-foreground-3);
  font-style: italic;
`,ae=a(V)`
  margin-bottom: 0.5rem;
`,ne=a(j)`
  && {
    gap: 0.375rem;
    font-size: 14px;
    flex-shrink: 0;
  }
`,se=({value:r,title:m,placeholder:c,className:t,showCopyButton:d=!0,truncate:n,maxLength:p=40,disabled:u=!1})=>{let[h,w]=(0,s.useState)(!1),T=n&&r?((i,k,f)=>{if((i=i.startsWith("https://")?i.slice(8):i).length<=f)return i;if(k==="middle"){let b=Math.ceil(f/2)-2,A=Math.floor(f/2)-1;return`${i.slice(0,b)}...${i.slice(-A)}`}return`${i.slice(0,f-3)}...`})(r,n,p):r;return(0,s.useEffect)((()=>{if(h){let i=setTimeout((()=>w(!1)),3e3);return()=>clearTimeout(i)}}),[h]),(0,e.jsxs)(re,{className:t,children:[m&&(0,e.jsx)(ae,{children:m}),(0,e.jsxs)(te,{$disabled:u,children:[(0,e.jsx)(ie,{children:r?(0,e.jsx)(H,{$disabled:u,title:r,children:T}):(0,e.jsx)(oe,{$disabled:u,children:c||"No value"})}),d&&r&&(0,e.jsx)(ne,{onClick:function(i){i.stopPropagation(),navigator.clipboard.writeText(r).then((()=>w(!0))).catch(console.error)},size:"sm",children:(0,e.jsxs)(e.Fragment,h?{children:["Copied",(0,e.jsx)(z,{size:14})]}:{children:["Copy",(0,e.jsx)(W,{size:14})]})})]})]})},le=({connectUri:r,loading:m,success:c,errorMessage:t,onBack:d,onClose:n,onOpenFarcaster:p})=>(0,e.jsx)(B,y.isMobile||m?y.isIOS?{title:t?t.message:"Sign in with Farcaster",subtitle:t?t.detail:"To sign in with Farcaster, please open the Farcaster app.",icon:E,iconVariant:"loading",iconLoadingStatus:{success:c,fail:!!t},primaryCta:r&&p?{label:"Open Farcaster app",onClick:p}:void 0,onBack:d,onClose:n,watermark:!0}:{title:t?t.message:"Signing in with Farcaster",subtitle:t?t.detail:"This should only take a moment",icon:E,iconVariant:"loading",iconLoadingStatus:{success:c,fail:!!t},onBack:d,onClose:n,watermark:!0,children:r&&y.isMobile&&(0,e.jsx)(ce,{children:(0,e.jsx)(P,{text:"Take me to Farcaster",url:r,color:"#8a63d2"})})}:{title:"Sign in with Farcaster",subtitle:"Scan with your phone's camera to continue.",onBack:d,onClose:n,watermark:!0,children:(0,e.jsxs)(de,{children:[(0,e.jsx)(me,{children:r?(0,e.jsx)(Q,{url:r,size:275,squareLogoElement:E}):(0,e.jsx)(he,{children:(0,e.jsx)(M,{})})}),(0,e.jsxs)(pe,{children:[(0,e.jsx)(ue,{children:"Or copy this link and paste it into a phone browser to open the Farcaster app."}),r&&(0,e.jsx)(se,{value:r,truncate:"end",maxLength:30,showCopyButton:!0,disabled:!0})]})]})}),Ie={component:()=>{let{authenticated:r,logout:m,ready:c,user:t}=U(),{lastScreen:d,navigate:n,navigateBack:p,setModalData:u}=D(),h=N(),{getAuthFlow:w,loginWithFarcaster:T,closePrivyModal:i,createAnalyticsEvent:k}=I(),[f,b]=(0,s.useState)(void 0),[A,J]=(0,s.useState)(!1),[S,K]=(0,s.useState)(!1),F=(0,s.useRef)([]),R=w(),O=R?.meta.connectUri;return(0,s.useEffect)((()=>{let g=Date.now(),_=setInterval((async()=>{let L=await R.pollForReady.execute(),X=Date.now()-g;if(L){clearInterval(_),J(!0);try{await T(),K(!0)}catch(o){let v={retryable:!1,message:"Authentication failed"};if(o?.privyErrorCode===l.ALLOWLIST_REJECTED)return void n("AllowlistRejectionScreen");if(o?.privyErrorCode===l.USER_LIMIT_REACHED)return console.error(new $(o).toString()),void n("UserLimitReachedScreen");if(o?.privyErrorCode===l.USER_DOES_NOT_EXIST)return void n("AccountNotFoundScreen");if(o?.privyErrorCode===l.LINKED_TO_ANOTHER_USER)v.detail=o.message??"This account has already been linked to another user.";else{if(o?.privyErrorCode===l.ACCOUNT_TRANSFER_REQUIRED&&o.data?.data?.nonce)return u({accountTransfer:{nonce:o.data?.data?.nonce,account:o.data?.data?.subject,displayName:o.data?.data?.account?.displayName,linkMethod:"farcaster",embeddedWalletAddress:o.data?.data?.otherUser?.embeddedWalletAddress,farcasterEmbeddedAddress:o.data?.data?.otherUser?.farcasterEmbeddedAddress}}),void n("LinkConflictScreen");o?.privyErrorCode===l.INVALID_CREDENTIALS?(v.retryable=!0,v.detail="Something went wrong. Try again."):o?.privyErrorCode===l.TOO_MANY_REQUESTS&&(v.detail="Too many requests. Please wait before trying again.")}b(v)}}else X>12e4&&(clearInterval(_),b({retryable:!0,message:"Authentication failed",detail:"The request timed out. Try again."}))}),2e3);return()=>{clearInterval(_),F.current.forEach((L=>clearTimeout(L)))}}),[]),(0,s.useEffect)((()=>{if(c&&r&&S&&t){if(h?.legal.requireUsersAcceptTerms&&!t.hasAcceptedTerms){let g=setTimeout((()=>{n("AffirmativeConsentScreen")}),x);return()=>clearTimeout(g)}S&&(q(t,h.embeddedWallets)?F.current.push(setTimeout((()=>{u({createWallet:{onSuccess:()=>{},onFailure:g=>{console.error(g),k({eventName:"embedded_wallet_creation_failure_logout",payload:{error:g,screen:"FarcasterConnectStatusScreen"}}),m()},callAuthOnSuccessOnClose:!0}}),n("EmbeddedWalletOnAccountCreateScreen")}),x)):F.current.push(setTimeout((()=>i({shouldCallAuthOnSuccess:!0,isSuccess:!0})),x)))}}),[S,c,r,t]),(0,e.jsx)(le,{connectUri:O,loading:A,success:S,errorMessage:f,onBack:d?p:void 0,onClose:i,onOpenFarcaster:()=>{O&&(window.location.href=O)}})}},ce=a.div`
  margin-top: 24px;
`,de=a.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
`,me=a.div`
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 275px;
`,pe=a.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
`,ue=a.div`
  font-size: 0.875rem;
  text-align: center;
  color: var(--privy-color-foreground-2);
`,he=a.div`
  position: relative;
  width: 82px;
  height: 82px;
`;export{Ie as FarcasterConnectStatusScreen,le as FarcasterConnectStatusView,Ie as default};
