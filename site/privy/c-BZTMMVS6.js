import{a as M}from"./c-PQXHTLX6.js";import{a as z}from"./c-UD2CI5D7.js";import{a as $}from"./c-AL3PKSPP.js";import{a as S}from"./c-YUEVV4PO.js";import{a as W}from"./c-QNA2K6DX.js";import{a as g}from"./c-YBP4CZSU.js";import{a as m}from"./c-2MQ6AKZW.js";import"./c-F2M6QL3Y.js";import{d as p,f as A,j as f,l as h}from"./c-EOAJVKNP.js";import"./c-3ZJETHS3.js";import"./c-TK45UUBT.js";import"./c-5AQXWU74.js";import"./c-FKNR4ZMH.js";import{b as C}from"./c-65SYQ2BY.js";import{b as i}from"./c-LC7NBPXT.js";import{Ca as b,wb as k}from"./c-Z3FRICV3.js";import"./c-FYFAMDSG.js";import{a as B,b as N}from"./c-3POUIAFT.js";import"./c-K4BTFUAC.js";import"./c-DBE6YW6D.js";import"./c-F3P6SX6T.js";import"./c-4ERX45K7.js";import{e as w}from"./c-7SW4JVF5.js";var e=w(N(),1);var u=w(B(),1);var P=i.span`
  && {
    width: 82px;
    height: 82px;
    border-width: 4px;
    border-style: solid;
    border-color: ${r=>r.color??"var(--privy-color-accent)"};
    border-radius: 50%;
    display: inline-block;
    box-sizing: border-box;
    animation: rotation 1.2s linear infinite;
    transition: border-color 800ms;
  }
`;function F(r){return(0,e.jsxs)("svg",{xmlns:"http://www.w3.org/2000/svg",width:"24",height:"24",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor","stroke-width":"2","stroke-linecap":"round","stroke-linejoin":"round",...r,children:[(0,e.jsx)("circle",{cx:"12",cy:"12",r:"10"}),(0,e.jsx)("line",{x1:"12",x2:"12",y1:"8",y2:"12"}),(0,e.jsx)("line",{x1:"12",x2:"12.01",y1:"16",y2:"16"})]})}var j=({onTransfer:r,isTransferring:n,transferSuccess:o})=>(0,e.jsx)(p,{...o?{success:!0,children:"Success!"}:{warn:!0,loading:n,onClick:r,children:"Transfer and delete account"}}),E=i.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding-bottom: 16px;
`,y=i.div`
  display: flex;
  flex-direction: column;
  && p {
    font-size: 14px;
  }
  width: 100%;
  gap: 16px;
`,L=i.div`
  display: flex;
  cursor: pointer;
  align-items: center;
  width: 100%;
  border: 1px solid var(--privy-color-foreground-4) !important;
  border-radius: var(--privy-border-radius-md);
  padding: 8px 10px;
  font-size: 14px;
  font-weight: 500;
  gap: 8px;
`,U=i(S)`
  position: relative;
  width: ${({$iconSize:r})=>`${r}px`};
  height: ${({$iconSize:r})=>`${r}px`};
  color: var(--privy-color-foreground-3);
  margin-left: auto;
`,_=i($)`
  position: relative;
  width: 15px;
  height: 15px;
  color: var(--privy-color-foreground-3);
  margin-left: auto;
`,V=i.ol`
  display: flex;
  flex-direction: column;
  font-size: 14px;
  width: 100%;
  text-align: left;
`,I=i.li`
  font-size: 14px;
  list-style-type: auto;
  list-style-position: outside;
  margin-left: 1rem;
  margin-bottom: 0.5rem; /* Adjust the margin as needed */

  &:last-child {
    margin-bottom: 0; /* Remove margin from the last item */
  }
`,q=i.div`
  position: relative;
  width: 60px;
  height: 60px;
  margin: 10px;
  display: flex;
  justify-content: center;
  align-items: center;
`,G=()=>(0,e.jsx)(q,{children:(0,e.jsx)(U,{$iconSize:60})}),H=({address:r,onClose:n,onRetry:o,onTransfer:c,isTransferring:l,transferSuccess:d})=>{let{defaultChain:t}=k(),a=t.blockExplorers?.default.url??"https://etherscan.io";return(0,e.jsxs)(e.Fragment,{children:[(0,e.jsx)(f,{onClose:n,backFn:o}),(0,e.jsxs)(E,{children:[(0,e.jsx)(G,{}),(0,e.jsxs)(y,{children:[(0,e.jsx)("h3",{children:"Check account assets before transferring"}),(0,e.jsx)("p",{children:"Before transferring, ensure there are no assets in the other account. Assets in that account will not transfer automatically and may be lost."}),(0,e.jsxs)(V,{children:[(0,e.jsx)("p",{children:" To check your balance, you can:"}),(0,e.jsx)(I,{children:"Log out and log back into the other account, or "}),(0,e.jsxs)(I,{children:["Copy your wallet address and use a"," ",(0,e.jsx)("u",{children:(0,e.jsx)("a",{target:"_blank",href:a,children:"block explorer"})})," ","to see if the account holds any assets."]})]}),(0,e.jsxs)(L,{onClick:()=>navigator.clipboard.writeText(r).catch(console.error),children:[(0,e.jsx)(m,{color:"var(--privy-color-foreground)",strokeWidth:2,height:"28px",width:"28px"}),(0,e.jsx)(g,{address:r,showCopyIcon:!1}),(0,e.jsx)(_,{})]}),(0,e.jsx)(j,{onTransfer:c,isTransferring:l,transferSuccess:d})]})]}),(0,e.jsx)(h,{})]})},le={component:()=>{let{initiateAccountTransfer:r,closePrivyModal:n}=b(),{data:o,navigate:c,lastScreen:l,setModalData:d}=C(),[t,a]=(0,u.useState)(void 0),[s,D]=(0,u.useState)(!1),[x,T]=(0,u.useState)(!1),v=async()=>{try{if(!o?.accountTransfer?.nonce||!o?.accountTransfer?.account)throw Error("missing account transfer inputs");T(!0),await r({nonce:o?.accountTransfer?.nonce,account:o?.accountTransfer?.account,accountType:o?.accountTransfer?.linkMethod,externalWalletMetadata:o?.accountTransfer?.externalWalletMetadata,telegramWebAppData:o?.accountTransfer?.telegramWebAppData,telegramAuthResult:o?.accountTransfer?.telegramAuthResult,farcasterEmbeddedAddress:o?.accountTransfer?.farcasterEmbeddedAddress,oAuthUserInfo:o?.accountTransfer?.oAuthUserInfo}),D(!0),T(!1),setTimeout(n,1e3)}catch(R){d({errorModalData:{error:R,previousScreen:l||"LinkConflictScreen"}}),c("ErrorScreen",!0)}};return t?(0,e.jsx)(H,{address:t,onClose:n,onRetry:()=>a(void 0),onTransfer:v,isTransferring:x,transferSuccess:s}):(0,e.jsx)(J,{onClose:n,onInfo:()=>a(o?.accountTransfer?.embeddedWalletAddress),onContinue:()=>a(o?.accountTransfer?.embeddedWalletAddress),onTransfer:v,isTransferring:x,transferSuccess:s,data:o})}},J=({onClose:r,onContinue:n,onInfo:o,onTransfer:c,transferSuccess:l,isTransferring:d,data:t})=>{if(!t?.accountTransfer?.linkMethod||!t?.accountTransfer?.displayName)return;let a={method:t?.accountTransfer?.linkMethod,handle:t?.accountTransfer?.displayName,disclosedAccount:t?.accountTransfer?.embeddedWalletAddress?{type:"wallet",handle:t?.accountTransfer?.embeddedWalletAddress}:void 0};return(0,e.jsxs)(e.Fragment,{children:[(0,e.jsx)(f,{closeable:!0}),(0,e.jsxs)(E,{children:[(0,e.jsx)(M,{children:(0,e.jsxs)("div",{children:[(0,e.jsx)(P,{color:"var(--privy-color-error)"}),(0,e.jsx)(W,{height:38,width:38,stroke:"var(--privy-color-error)"})]})}),(0,e.jsxs)(y,{children:[(0,e.jsxs)("h3",{children:[(function(s){switch(s){case"sms":return"Phone number";case"email":return"Email address";case"siwe":return"Wallet address";case"siws":return"Solana wallet address";case"linkedin":return"LinkedIn profile";case"google":case"apple":case"discord":case"github":case"instagram":case"spotify":case"tiktok":case"line":case"twitch":case"twitter":case"telegram":case"farcaster":return`${z(s.replace("_oauth",""))} profile`;default:return s.startsWith("privy:")?"Cross-app account":s}})(a.method)," is associated with another account"]}),(0,e.jsxs)("p",{children:["Do you want to transfer",(0,e.jsx)("b",{children:a.handle?` ${a.handle}`:""})," to this account instead? This will delete your other account."]}),(0,e.jsx)(K,{onClick:o,disclosedAccount:a.disclosedAccount})]}),(0,e.jsxs)(y,{style:{gap:12,marginTop:12},children:[t?.accountTransfer?.embeddedWalletAddress?(0,e.jsx)(p,{onClick:n,children:"Continue"}):(0,e.jsx)(j,{onTransfer:c,transferSuccess:l,isTransferring:d}),(0,e.jsx)(A,{onClick:r,children:"No thanks"})]})]}),(0,e.jsx)(h,{})]})};function K({disclosedAccount:r,onClick:n}){return r?(0,e.jsxs)(L,{onClick:n,children:[(0,e.jsx)(m,{color:"var(--privy-color-foreground)",strokeWidth:2,height:"28px",width:"28px"}),(0,e.jsx)(g,{address:r.handle,showCopyIcon:!1}),(0,e.jsx)(F,{width:15,height:15,color:"var(--privy-color-foreground-3)",style:{marginLeft:"auto"}})]}):null}export{le as LinkConflictScreen,J as LinkConflictScreenView,le as default};
