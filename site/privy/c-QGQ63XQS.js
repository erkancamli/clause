import{a as P,b as z,c as V}from"./c-FNNBAGIO.js";import{a as Y}from"./c-2VVWJYS7.js";import"./c-ZJL7Y5HR.js";import{b as F}from"./c-B5BCMJ7E.js";import{a as g}from"./c-FYLEYBR7.js";import"./c-MB24CLN6.js";import{J as D,d as I,l as U,u as W}from"./c-F2M6QL3Y.js";import"./c-G7QKMXDE.js";import"./c-EOAJVKNP.js";import{a as Q}from"./c-TY233LCP.js";import{c as L}from"./c-35MSG53D.js";import{a as _}from"./c-TCALT4TQ.js";import"./c-R2JM2JIB.js";import"./c-IR2Q2AZQ.js";import"./c-RROTPPQ4.js";import"./c-2Z7ML7DV.js";import"./c-TEZKH2R4.js";import"./c-3ZJETHS3.js";import"./c-TK45UUBT.js";import"./c-5AQXWU74.js";import"./c-FKNR4ZMH.js";import{b as j}from"./c-65SYQ2BY.js";import{b}from"./c-LC7NBPXT.js";import{Ab as T,ta as B}from"./c-Z3FRICV3.js";import"./c-FYFAMDSG.js";import{a as G,b as J}from"./c-3POUIAFT.js";import"./c-K4BTFUAC.js";import"./c-DBE6YW6D.js";import"./c-F3P6SX6T.js";import"./c-4ERX45K7.js";import{e as S}from"./c-7SW4JVF5.js";var t=S(J(),1),m=S(G(),1);var $=S(Q(),1);var Z=e=>{try{return e.location.origin}catch{return}},ee=({data:e,onClose:a})=>(0,t.jsx)(g,{showClose:!0,onClose:a,title:"Initiate bank transfer",subtitle:"Use the details below to complete a bank transfer from your bank.",primaryCta:{label:"Done",onClick:a},watermark:!1,footerText:"Exchange rates and fees are set when you authorize and determine the amount you receive. You'll see the applicable rates and fees for your transaction separately",children:(0,t.jsx)(te,{children:(L[e.deposit_instructions.asset]||[]).map((([l,y],h)=>{let f=e.deposit_instructions[l];if(!f||Array.isArray(f))return null;let d=l==="asset"?f.toUpperCase():f,n=d.length>100?`${d.slice(0,9)}...${d.slice(-9)}`:d;return(0,t.jsxs)(re,{children:[(0,t.jsx)(oe,{children:y}),(0,t.jsx)(F,{value:d,includeChildren:$.isMobile,children:(0,t.jsx)(se,{children:n})})]},h)}))})}),te=b.ol`
  border-color: var(--privy-color-border-default);
  border-width: 1px;
  border-radius: var(--privy-border-radius-mdlg);
  border-style: solid;
  display: flex;
  flex-direction: column;

  && {
    padding: 0 1rem;
  }
`,re=b.li`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 0;

  &:not(:first-of-type) {
    border-top: 1px solid var(--privy-color-border-default);
  }

  & > {
    :nth-child(1) {
      flex-basis: 30%;
    }

    :nth-child(2) {
      flex-basis: 60%;
    }
  }
`,oe=b.span`
  color: var(--privy-color-foreground);
  font-kerning: none;
  font-variant-numeric: lining-nums proportional-nums;
  font-feature-settings: 'calt' off;

  /* text-xs/font-regular */
  font-size: 0.75rem;
  font-style: normal;
  font-weight: 400;
  line-height: 1.125rem; /* 150% */

  text-align: left;
  flex-shrink: 0;
`,se=b.span`
  color: var(--privy-color-foreground);
  font-kerning: none;
  font-feature-settings: 'calt' off;

  /* text-sm/font-medium */
  font-size: 0.875rem;
  font-style: normal;
  font-weight: 500;
  line-height: 1.375rem; /* 157.143% */

  text-align: right;
  word-break: break-all;
`,ae=({onClose:e})=>(0,t.jsx)(g,{showClose:!0,onClose:e,icon:U,iconVariant:"error",title:"Something went wrong",subtitle:"We couldn't complete account setup. This isn't caused by anything you did.",primaryCta:{label:"Close",onClick:e},watermark:!0}),ie=({onClose:e,reason:a})=>{let l=a?a.charAt(0).toLowerCase()+a.slice(1):void 0;return(0,t.jsx)(g,{showClose:!0,onClose:e,icon:U,iconVariant:"error",title:"Identity verification failed",subtitle:l?`We can't complete identity verification because ${l}. Please try again or contact support for assistance.`:"We couldn't verify your identity. Please try again or contact support for assistance.",primaryCta:{label:"Close",onClick:e},watermark:!0})},ne=({onClose:e,email:a})=>(0,t.jsx)(g,{showClose:!0,onClose:e,icon:W,title:"Identity verification in progress",subtitle:"We're waiting for Persona to approve your identity verification. This usually takes a few minutes, but may take up to 24 hours.",primaryCta:{label:"Done",onClick:e},watermark:!0,children:(0,t.jsxs)(Y,{theme:"light",children:["You'll receive an email at ",a," once approved with instructions for completing your deposit."]})}),le=({onClose:e,onAcceptTerms:a,isLoading:l})=>(0,t.jsx)(g,{showClose:!0,onClose:e,icon:D,title:"Verify your identity to continue",subtitle:"Finish verification with Persona \u2014 it takes just a few minutes and requires a government ID.",helpText:(0,t.jsxs)(t.Fragment,{children:[`This app uses Bridge to securely connect accounts and move funds. By clicking "Accept," you agree to Bridge's`," ",(0,t.jsx)("a",{href:"https://www.bridge.xyz/legal",target:"_blank",rel:"noopener noreferrer",children:"Terms of Service"})," ","and"," ",(0,t.jsx)("a",{href:"https://www.bridge.xyz/legal/row-privacy-policy/bridge-building-limited",target:"_blank",rel:"noopener noreferrer",children:"Privacy Policy"}),"."]}),primaryCta:{label:"Accept and continue",onClick:a,loading:l},watermark:!0}),ce=({onClose:e})=>(0,t.jsx)(g,{showClose:!0,onClose:e,icon:I,iconVariant:"success",title:"Identity verified successfully",subtitle:"We've successfully verified your identity. Now initiate a bank transfer to view instructions.",primaryCta:{label:"Initiate bank transfer",onClick:()=>{},loading:!0},watermark:!0}),ue=({opts:e,onClose:a,onBack:l,onEditSourceAsset:y,onSelectAmount:h,isLoading:f})=>(0,t.jsxs)(g,{showClose:!0,onClose:a,showBack:!!l,onBack:l,headerTitle:`Buy ${e.destination.asset.toLocaleUpperCase()}`,primaryCta:{label:"Continue",onClick:h,loading:f},watermark:!0,children:[(0,t.jsx)(P,{currency:e.source.selectedAsset,inputMode:"decimal",autoFocus:!0}),(0,t.jsx)(z,{selectedAsset:e.source.selectedAsset,onEditSourceAsset:y})]}),de=({onClose:e,onBack:a,onAcceptTerms:l,onSelectAmount:y,onSelectSource:h,onEditSourceAsset:f,opts:d,state:n,email:v,isLoading:i})=>n.status==="select-amount"?(0,t.jsx)(ue,{onClose:e,onBack:a,onSelectAmount:y,onEditSourceAsset:f,opts:d,isLoading:i}):n.status==="select-source-asset"?(0,t.jsx)(V,{onSelectSource:h,opts:d,isLoading:i}):n.status==="kyc-prompt"?(0,t.jsx)(le,{onClose:e,onAcceptTerms:l,opts:d,isLoading:i}):n.status==="kyc-incomplete"?(0,t.jsx)(ne,{onClose:e,email:v}):n.status==="kyc-success"?(0,t.jsx)(ce,{onClose:e}):n.status==="kyc-error"?(0,t.jsx)(ie,{onClose:e,reason:n.reason}):n.status==="account-details"?(0,t.jsx)(ee,{onClose:e,data:n.data}):n.status==="create-customer-error"||n.status==="get-customer-error"?(0,t.jsx)(ae,{onClose:e}):null,Se={component:()=>{let{user:e}=T(),a=j().data;if(!a?.FundWithBankDepositScreen)throw Error("Missing data");let{onSuccess:l,onFailure:y,onBack:h,opts:f,createOrUpdateCustomer:d,getCustomer:n,getOrCreateVirtualAccount:v}=a.FundWithBankDepositScreen,[i,E]=(0,m.useState)(f),[k,r]=(0,m.useState)({status:"select-amount"}),[A,u]=(0,m.useState)(null),[M,s]=(0,m.useState)(!1),w=(0,m.useRef)(null),R=(0,m.useCallback)((async()=>{let o;s(!0),u(null);try{o=await n({kycRedirectUrl:window.location.origin})}catch(c){if(!c||typeof c!="object"||!("status"in c)||c.status!==404)return r({status:"get-customer-error"}),u(c),void s(!1)}if(!o)try{o=await d({hasAcceptedTerms:!1,kycRedirectUrl:window.location.origin})}catch(c){return r({status:"create-customer-error"}),u(c),void s(!1)}if(!o)return r({status:"create-customer-error"}),u(Error("Unable to create customer")),void s(!1);if(o.status==="not_started"&&o.kyc_url)return r({status:"kyc-prompt",kycUrl:o.kyc_url}),void s(!1);if(o.status==="not_started")return r({status:"get-customer-error"}),u(Error("Unexpected user state")),void s(!1);if(o.status==="rejected")return r({status:"kyc-error",reason:o.rejection_reasons?.[0]?.reason}),u(Error("User KYC rejected.")),void s(!1);if(o.status==="incomplete")return r({status:"kyc-incomplete"}),void s(!1);if(o.status!=="active")return r({status:"get-customer-error"}),u(Error("Unexpected user state")),void s(!1);o.status;try{let c=await v({destination:i.destination,provider:i.provider,source:{asset:i.source.selectedAsset}});r({status:"account-details",data:c})}catch(c){return r({status:"create-customer-error"}),u(c),void s(!1)}}),[i]),K=(0,m.useCallback)((async()=>{if(u(null),s(!0),k.status!=="kyc-prompt")return u(Error("Unexpected state")),void s(!1);let o=_({location:k.kycUrl});if(await d({hasAcceptedTerms:!0}),!o)return u(Error("Unable to begin kyc flow.")),s(!1),void r({status:"create-customer-error"});w.current=new AbortController;let c=await(async(p,H)=>{let x=await B({operation:async()=>({done:Z(p)===window.location.origin,closed:p.closed}),until:({done:N,closed:X})=>N||X,delay:0,interval:500,attempts:360,signal:H});return x.status==="aborted"?(p.close(),{status:"aborted"}):x.status==="max_attempts"?{status:"timeout"}:x.result.done?(p.close(),{status:"redirected"}):{status:"closed"}})(o,w.current.signal);if(c.status==="aborted")return;if(c.status==="closed")return void s(!1);c.status;let C=await B({operation:()=>n({}),until:p=>p.status==="active"||p.status==="rejected",delay:0,interval:2e3,attempts:60,signal:w.current.signal});if(C.status!=="aborted"){if(C.status==="max_attempts")return r({status:"kyc-incomplete"}),void s(!1);if(C.status,C.result.status==="rejected")return r({status:"kyc-error",reason:C.result.rejection_reasons?.[0]?.reason}),u(Error("User KYC rejected.")),void s(!1);if(C.result.status!=="active")return r({status:"kyc-incomplete"}),void s(!1);o.closed||o.close(),C.result.status;try{r({status:"kyc-success"});let p=await v({destination:i.destination,provider:i.provider,source:{asset:i.source.selectedAsset}});r({status:"account-details",data:p})}catch(p){r({status:"create-customer-error"}),u(p)}finally{s(!1)}}}),[r,u,s,d,v,k,i,w]),O=(0,m.useCallback)((o=>{r({status:"select-amount"}),E({...i,source:{...i.source,selectedAsset:o}})}),[r,E]),q=(0,m.useCallback)((()=>{r({status:"select-source-asset"})}),[r]);return(0,t.jsx)(de,{onClose:(0,m.useCallback)((async()=>{w.current?.abort(),!i.showBackButton||k.status!=="select-amount"&&k.status!=="select-source-asset"?A?y(A):await l():y(Error("User cancelled funding"))}),[A,w,y,l,i.showBackButton,k.status]),onBack:h,opts:i,state:k,isLoading:M,email:e.email.address,onAcceptTerms:K,onSelectAmount:R,onSelectSource:O,onEditSourceAsset:q})}};export{Se as FundWithBankDepositScreen,Se as default};
