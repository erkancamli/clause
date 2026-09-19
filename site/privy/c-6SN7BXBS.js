import{a as T,b as g}from"./c-JYDSSOSI.js";import{a as k}from"./c-FYLEYBR7.js";import{G as S,i as z,s as b}from"./c-F2M6QL3Y.js";import{L as N}from"./c-TCALT4TQ.js";import{a as x,h as u}from"./c-TK45UUBT.js";import{b as A}from"./c-65SYQ2BY.js";import{a as w,b as o,h as L}from"./c-LC7NBPXT.js";import{Ab as P,Ca as I}from"./c-Z3FRICV3.js";import{a as j,b as B}from"./c-3POUIAFT.js";import{e as E}from"./c-7SW4JVF5.js";var e=E(B(),1);var l=E(j(),1);var D=({passkeys:s,name:d,isLoading:m,errorReason:h,success:c,expanded:n,onLinkPasskey:y,onUnlinkPasskey:i,onExpand:r,onBack:t,onClose:a})=>c?(0,e.jsx)(k,{title:"Passkeys updated",icon:z,iconVariant:"success",primaryCta:{label:"Done",onClick:a},onClose:a,watermark:!0}):n?(0,e.jsx)(k,{icon:b,title:"Your passkeys",onBack:t,onClose:a,watermark:!0,children:(0,e.jsx)(U,{passkeys:s,expanded:n,onUnlink:i,onExpand:r})}):(0,e.jsxs)(k,{icon:b,title:"Set up passkey verification",subtitle:"Verify with passkey",primaryCta:{label:"Add new passkey",onClick:y,loading:m},onClose:a,watermark:!0,helpText:h||void 0,children:[s.length===0?(0,e.jsx)($,{}):(0,e.jsx)(M,{children:(0,e.jsx)(U,{passkeys:s,expanded:n,onUnlink:i,onExpand:r})}),d?(0,e.jsxs)(_,{children:[(0,e.jsx)(O,{children:"New Passkey Name"}),(0,e.jsx)(V,{children:d})]}):null]}),M=o.div`
  margin-bottom: 0.75rem;
`,_=o.div`
  margin-top: 0.25rem;
`,O=o.div`
  color: var(--privy-color-foreground-2);
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1rem;
  margin-bottom: 0.25rem;
`,V=o.div`
  color: var(--privy-color-foreground);
  font-size: 0.875rem;
  line-height: 1.25rem;
`,U=({passkeys:s,expanded:d,onUnlink:m,onExpand:h})=>{let[c,n]=(0,l.useState)([]),y=d?s.length:2;return(0,e.jsxs)("div",{children:[(0,e.jsx)(K,{children:"Your passkeys"}),(0,e.jsxs)(Y,{children:[s.slice(0,y).map((i=>{return(0,e.jsxs)(H,{children:[(0,e.jsxs)("div",{children:[(0,e.jsx)(q,{children:(r=i,r.authenticatorName?r.createdWithBrowser?`${r.authenticatorName} on ${r.createdWithBrowser}`:r.authenticatorName:r.createdWithBrowser?r.createdWithOs?`${r.createdWithBrowser} on ${r.createdWithOs}`:`${r.createdWithBrowser}`:"Unknown device")}),(0,e.jsxs)(G,{children:["Last used:"," ",(i.latestVerifiedAt??i.firstVerifiedAt)?.toLocaleString()??"N/A"]})]}),(0,e.jsx)(Q,{disabled:c.includes(i.credentialId),onClick:()=>(async t=>{n((a=>a.concat([t]))),await m(t),n((a=>a.filter((f=>f!==t))))})(i.credentialId),children:c.includes(i.credentialId)?(0,e.jsx)(L,{}):(0,e.jsx)(S,{size:16})})]},i.credentialId);var r})),s.length>2&&!d&&(0,e.jsx)(R,{onClick:h,children:"View all"})]})]})},$=()=>(0,e.jsxs)(T,{style:{color:"var(--privy-color-foreground)"},children:[(0,e.jsx)(g,{children:"Verify with Touch ID, Face ID, PIN, or hardware key"}),(0,e.jsx)(g,{children:"Takes seconds to set up and use"}),(0,e.jsx)(g,{children:"Use your passkey to verify transactions and login to your account"})]}),ce={component:()=>{let{user:s}=P(),{unlink:d}=N(),{linkWithPasskey:m,closePrivyModal:h}=I(),{data:c}=A(),n=s?.linkedAccounts.filter((p=>p.type==="passkey")),[y,i]=(0,l.useState)(!1),[r,t]=(0,l.useState)(""),[a,f]=(0,l.useState)(!1),[W,v]=(0,l.useState)(!1);return(0,l.useEffect)((()=>{n.length===0&&v(!1)}),[n.length]),(0,e.jsx)(D,{passkeys:n,name:c?.passkeyAuthModalData?.name,isLoading:y,errorReason:r,success:a,expanded:W,onLinkPasskey:()=>{i(!0),m({name:c?.passkeyAuthModalData?.name}).then((()=>f(!0))).catch((p=>{if(p instanceof x){if(p.privyErrorCode===u.CANNOT_LINK_MORE_OF_TYPE)return void t("Cannot link more passkeys to account.");if(p.privyErrorCode===u.PASSKEY_NOT_ALLOWED)return void t("Passkey request timed out or rejected by user.")}t("Unknown error occurred.")})).finally((()=>{i(!1)}))},onUnlinkPasskey:async p=>(i(!0),await d({credentialId:p}).then((()=>f(!0))).catch((C=>{C instanceof x&&C.privyErrorCode===u.MISSING_MFA_CREDENTIALS?t("Cannot unlink a passkey enrolled in MFA"):t("Unknown error occurred.")})).finally((()=>{i(!1)}))),onExpand:()=>v(!0),onBack:()=>v(!1),onClose:()=>h()})}},pe=o.div`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 180px;
  height: 90px;
  border-radius: 50%;
  svg + svg {
    margin-left: 12px;
  }
  > svg {
    z-index: 2;
    color: var(--privy-color-accent) !important;
    stroke: var(--privy-color-accent) !important;
    fill: var(--privy-color-accent) !important;
  }
`,F=w`
  && {
    width: 100%;
    font-size: 0.875rem;
    line-height: 1rem;

    /* Tablet and Up */
    @media (min-width: 440px) {
      font-size: 14px;
    }

    display: flex;
    gap: 12px;
    justify-content: center;

    padding: 6px 8px;
    background-color: var(--privy-color-background);
    transition: background-color 200ms ease;
    color: var(--privy-color-accent) !important;

    :focus {
      outline: none;
      box-shadow: none;
    }
  }
`,R=o.button`
  ${F}
`,Y=o.div`
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.8rem;
  padding: 0.5rem 0 0;
  flex-grow: 1;
  width: 100%;
`,K=o.div`
  line-height: 20px;
  height: 20px;
  font-size: 1em;
  font-weight: 450;
  display: flex;
  justify-content: flex-start;
  width: 100%;
`,q=o.div`
  font-size: 1em;
  line-height: 1.3em;
  font-weight: 500;
  color: var(--privy-color-foreground-2);
  padding: 0.2em 0;
`,G=o.div`
  font-size: 0.875rem;
  line-height: 1rem;
  color: var(--privy-color-foreground-2);
  padding: 0.2em 0;
`,H=o.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1em;
  gap: 10px;
  font-size: 0.875rem;
  line-height: 1rem;
  text-align: left;
  border-radius: 8px;
  border: 1px solid var(--privy-color-border-default) !important;
  width: 100%;
  height: 5em;
`,J=w`
  :focus,
  :hover,
  :active {
    outline: none;
  }
  display: flex;
  width: 2em;
  height: 2em;
  justify-content: center;
  align-items: center;
  svg {
    color: var(--privy-color-error);
  }
  svg:hover {
    color: var(--privy-color-foreground-3);
  }
`,Q=o.button`
  ${J}
`;export{D as a,ce as b,pe as c,R as d};
