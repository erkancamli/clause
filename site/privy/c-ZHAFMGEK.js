import{a as w,b as S,c as T}from"./c-QOGEEQV2.js";import{a as _,b as D}from"./c-ISUCAI45.js";import{a as g,e as a,g as n}from"./c-HLTOMO4I.js";import{d as Y}from"./c-6MOKGNZB.js";import"./c-FYLEYBR7.js";import"./c-MB24CLN6.js";import{L as G,o as E,w as F}from"./c-F2M6QL3Y.js";import{a as O}from"./c-G7QKMXDE.js";import"./c-EOAJVKNP.js";import{n as x,o as L}from"./c-35MSG53D.js";import"./c-TCALT4TQ.js";import"./c-R2JM2JIB.js";import"./c-IR2Q2AZQ.js";import"./c-RROTPPQ4.js";import"./c-2Z7ML7DV.js";import"./c-TEZKH2R4.js";import"./c-3ZJETHS3.js";import"./c-TK45UUBT.js";import"./c-5AQXWU74.js";import"./c-FKNR4ZMH.js";import{b as k}from"./c-65SYQ2BY.js";import{b as l}from"./c-LC7NBPXT.js";import{wb as b}from"./c-Z3FRICV3.js";import"./c-FYFAMDSG.js";import{a as z,b as B}from"./c-3POUIAFT.js";import"./c-K4BTFUAC.js";import"./c-DBE6YW6D.js";import"./c-F3P6SX6T.js";import"./c-4ERX45K7.js";import{e as A}from"./c-7SW4JVF5.js";var r=A(B(),1);var e=A(z(),1);var tr={component:()=>{let t=x(),{onUserCloseViaDialogOrKeybindRef:p}=k(),R=b(),i=(0,e.useRef)(!1),d=w(S),P=w(T),[j,I]=(0,e.useState)(!1),h=d?"APPLE_PAY":d===!1&&P?"GOOGLE_PAY":null,f=d===!0||d===!1&&P!==void 0,y=!t?.startFiat||f||j;(0,e.useEffect)((()=>{let C=window.setTimeout((()=>I(!0)),2e3);return()=>window.clearTimeout(C)}),[]),(0,e.useEffect)((()=>{t&&(i.current=!1)}),[t]);let v=(0,e.useRef)(null);(0,e.useEffect)((()=>{t&&!t.error&&y&&v.current!==t&&(v.current=t,t.recordRowsViewed?.({walletPay:t.startFiat?h:void 0,walletPayTimedOut:t.startFiat?!f:void 0}))}),[y,t,h,f]);let o=(0,e.useCallback)((async()=>{!i.current&&t&&(i.current=!0,L(),await t.onCancel())}),[t]);if((0,e.useEffect)((()=>(p.current=o,()=>{p.current===o&&(p.current=null)})),[o,p]),!t)return null;if(t.error)return(0,r.jsx)(g,{title:"Unable to add funds",subtitle:t.error,showClose:!0,onClose:o,primaryCta:{label:"Close",onClick:o}});let u=async C=>{i.current||(i.current=!0,await t.startFiat?.(C))};return(0,r.jsx)(g,{title:"Pay with",subtitle:"Debit cards typically have higher success rates than credit cards, even with Apple Pay or Google Pay.",showClose:!0,onClose:o,children:y?(0,r.jsxs)(Y,{style:{marginTop:"1rem"},$colorScheme:R.appearance.palette.colorScheme,children:[t.startFiat&&(0,r.jsxs)(n,{onClick:()=>u("CREDIT_DEBIT_CARD"),children:[(0,r.jsx)(s,{children:(0,r.jsx)(E,{})}),(0,r.jsxs)(c,{children:[(0,r.jsx)(a,{children:"Debit or credit card"}),(0,r.jsx)(m,{children:"Less than 10 minutes"})]})]}),t.startFiat&&h==="APPLE_PAY"&&(0,r.jsxs)(n,{onClick:()=>u("APPLE_PAY"),children:[(0,r.jsx)(s,{children:(0,r.jsx)(_,{width:18,height:18})}),(0,r.jsxs)(c,{children:[(0,r.jsx)(a,{children:"Apple Pay"}),(0,r.jsx)(m,{children:"Less than 10 minutes"})]})]}),t.startFiat&&h==="GOOGLE_PAY"&&(0,r.jsxs)(n,{onClick:()=>u("GOOGLE_PAY"),children:[(0,r.jsx)(s,{children:(0,r.jsx)(D,{width:18,height:18})}),(0,r.jsxs)(c,{children:[(0,r.jsx)(a,{children:"Google Pay"}),(0,r.jsx)(m,{children:"Less than 10 minutes"})]})]}),t.startFiat&&(0,r.jsxs)(n,{onClick:()=>u("BANK"),children:[(0,r.jsx)(s,{children:(0,r.jsx)(F,{})}),(0,r.jsxs)(c,{children:[(0,r.jsx)(a,{children:"Bank account"}),(0,r.jsx)(m,{children:"1\u20132 days"})]})]}),t.startCrypto&&(0,r.jsxs)(n,{onClick:async()=>{i.current||(i.current=!0,await t.startCrypto?.())},children:[(0,r.jsx)(s,{children:(0,r.jsx)(G,{})}),(0,r.jsxs)(c,{children:[(0,r.jsx)(a,{children:"Crypto wallet or exchange"}),(0,r.jsx)(m,{children:"Instant"})]})]})]}):(0,r.jsx)(K,{children:(0,r.jsx)(O,{size:"50px"})})})}},K=l.div`
  display: flex;
  justify-content: center;
  align-items: center;
  margin-top: 1rem;
  min-height: 8rem;
`,s=l.span`
  width: 2rem;
  height: 2rem;
  border-radius: var(--privy-border-radius-full);
  background-color: var(--privy-color-background-2);
  color: var(--privy-color-icon-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;

  svg {
    width: 1.125rem;
    height: 1.125rem;
  }
`,c=l.span`
  display: flex;
  flex-direction: column;
  align-items: flex-start;
`,m=l.span`
  font-size: 0.875rem;
  line-height: 1.25rem;
  color: var(--privy-color-foreground-3);
`;export{tr as AddFundsSelectionScreen,tr as default};
