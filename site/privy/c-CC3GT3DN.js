import{a as z,b as I}from"./c-BZHLJRRR.js";import{a as k}from"./c-IX6DWULE.js";import{g as P}from"./c-LZ25EMVC.js";import{a as O}from"./c-FYLEYBR7.js";import"./c-MB24CLN6.js";import{F as N}from"./c-F2M6QL3Y.js";import"./c-G7QKMXDE.js";import"./c-EOAJVKNP.js";import{d as x,e as C}from"./c-5BKC3C2P.js";import"./c-3ZJETHS3.js";import"./c-TK45UUBT.js";import"./c-5AQXWU74.js";import"./c-FKNR4ZMH.js";import{b as M}from"./c-65SYQ2BY.js";import{b as m}from"./c-LC7NBPXT.js";import{Ab as L,Ca as D,Sa as U,U as f,ob as A}from"./c-Z3FRICV3.js";import{b as v}from"./c-FYFAMDSG.js";import{a as H,b as K}from"./c-3POUIAFT.js";import"./c-K4BTFUAC.js";import"./c-DBE6YW6D.js";import{oa as _,v as R}from"./c-F3P6SX6T.js";import"./c-4ERX45K7.js";import{e as b}from"./c-7SW4JVF5.js";var t=b(K(),1);var a=b(H(),1);var B=m.img`
  && {
    height: ${e=>e.size==="sm"?"65px":"140px"};
    width: ${e=>e.size==="sm"?"65px":"140px"};
    border-radius: 16px;
    margin-bottom: 12px;
  }
`,G=e=>{if(!R(e))return e;try{let i=_(e);return i.includes("\uFFFD")?e:i}catch{return e}},X=e=>{try{let i=v.decode(e),o=new TextDecoder().decode(i);return o.includes("\uFFFD")?e:o}catch{return e}},Y=e=>{let{types:i,primaryType:o,...l}=e.typedData;return(0,t.jsxs)(t.Fragment,{children:[(0,t.jsx)(ie,{data:l}),(0,t.jsx)(k,{text:(n=e.typedData,JSON.stringify(n,null,2)),itemName:"full payload to clipboard"})," "]});var n},Z=({method:e,messageData:i,copy:o,iconUrl:l,isLoading:n,success:u,walletProxyIsLoading:g,errorMessage:h,isCancellable:c,onSign:p,onCancel:S,onClose:d})=>(0,t.jsx)(O,{title:o.title,subtitle:o.description,showClose:!0,onClose:d,icon:N,iconVariant:"subtle",helpText:h?(0,t.jsx)(te,{children:h}):void 0,primaryCta:{label:o.buttonText,onClick:p,disabled:n||u||g,loading:n},secondaryCta:c?{label:"Not now",onClick:S,disabled:n||u||g}:void 0,watermark:!0,children:(0,t.jsxs)(P,{children:[l?(0,t.jsx)(B,{style:{alignSelf:"center"},size:"sm",src:l,alt:"app image"}):null,(0,t.jsxs)(ee,{children:[e==="personal_sign"&&(0,t.jsx)(j,{children:G(i)}),e==="eth_signTypedData_v4"&&(0,t.jsx)(Y,{typedData:i}),e==="solana_signMessage"&&(0,t.jsx)(j,{children:X(i)})]})]})}),xe={component:()=>{let{authenticated:e}=L(),{initializeWalletProxy:i,closePrivyModal:o}=D(),{navigate:l,data:n,onUserCloseViaDialogOrKeybindRef:u}=M(),[g,h]=(0,a.useState)(!0),[c,p]=(0,a.useState)(""),[S,d]=(0,a.useState)(),[E,T]=(0,a.useState)(null),[F,w]=(0,a.useState)(!1);(0,a.useEffect)((()=>{e||l("LandingScreen")}),[e]),(0,a.useEffect)((()=>{i(A).then((r=>{h(!1),r||(p("An error has occurred, please try again."),d(new C(new x(c,f.E32603_DEFAULT_INTERNAL_ERROR.eipCode))))}))}),[]);let{method:q,data:V,confirmAndSign:J,onSuccess:Q,onFailure:W,uiOptions:s}=n.signMessage,$={title:s?.title||"Sign message",description:s?.description||"Signing this message will not cost you any fees.",buttonText:s?.buttonText||"Sign and continue"},y=r=>{r?Q(r):W(S||new C(new x("The user rejected the request.",f.E4001_USER_REJECTED_REQUEST.eipCode))),o({shouldCallAuthOnSuccess:!1}),setTimeout((()=>{T(null),p(""),d(void 0)}),200)};return u.current=()=>{y(E)},(0,t.jsx)(Z,{method:q,messageData:V,copy:$,iconUrl:s?.iconUrl&&typeof s.iconUrl=="string"?s.iconUrl:void 0,isLoading:F,success:E!==null,walletProxyIsLoading:g,errorMessage:c,isCancellable:s?.isCancellable,onSign:async()=>{w(!0),p("");try{let r=await J();T(r),w(!1),setTimeout((()=>{y(r)}),U)}catch(r){console.error(r),p("An error has occurred, please try again."),d(new C(new x(c,f.E32603_DEFAULT_INTERNAL_ERROR.eipCode))),w(!1)}},onCancel:()=>y(null),onClose:()=>y(E)})}},ee=m.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
`,te=m.p`
  && {
    margin: 0;
    width: 100%;
    text-align: center;
    color: var(--privy-color-error-dark);
    font-size: 14px;
    line-height: 22px;
  }
`,ie=m(I)`
  margin-top: 0;
`,j=m(z)`
  margin-top: 0;
`;export{xe as SignRequestScreen,Z as SignRequestView,xe as default};
