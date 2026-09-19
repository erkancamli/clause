/* Privy's sign in window, and nothing else from Privy.

   The site is one hand written page with no build step. This file is the only
   part that needs one, because Privy's window is a React component. It is
   packed into site/privy.js and loaded only when someone presses "Continue
   with email, Google or a wallet"; nobody else downloads it.

   It exposes window.ClausePrivy with six calls:
     start(appId, theme)  mount Privy, resolves when it knows the session state
     login()              open the window, resolves with an access token
     token()              the current access token, or null if signed out
     logout()             end the Privy session on this browser
     linkX()              run X's sign in inside Privy and join the X account
                          to this Privy user; resolves with an identity token
                          that names the joined accounts, signed by Privy
     identityToken()      the current identity token, or null

   No embedded wallet is created: purchases are signed by the key the page
   makes on the device, so a Privy wallet would be a second key doing nothing. */
import React, { useEffect } from "react";
import { createRoot } from "react-dom/client";
import { PrivyProvider, usePrivy, useLogin, useLinkAccount, getIdentityToken } from "@privy-io/react-auth";

const state = { ready: null, api: null, pending: null, linking: null };

function Bridge({ onReady }) {
  const { ready, authenticated, getAccessToken, logout } = usePrivy();
  const { linkTwitter } = useLinkAccount({
    onSuccess: async () => {
      const p = state.linking; state.linking = null;
      if (!p) return;
      try { p.resolve(await getIdentityToken()); } catch (e) { p.reject(e); }
    },
    onError: (error) => {
      const p = state.linking; state.linking = null;
      if (p) p.reject(new Error(String(error || "closed")));
    },
  });
  const { login } = useLogin({
    onComplete: async () => {
      const p = state.pending; state.pending = null;
      if (!p) return;
      try { p.resolve(await getAccessToken()); } catch (e) { p.reject(e); }
    },
    onError: (error) => {
      const p = state.pending; state.pending = null;
      if (p) p.reject(new Error(String(error || "closed")));
    },
  });
  useEffect(() => {
    state.api = { authenticated, getAccessToken, logout, login, linkTwitter };
    if (ready) onReady();
  }, [ready, authenticated, getAccessToken, logout, login, linkTwitter]);
  return null;
}

function start(appId, theme) {
  if (state.ready) return state.ready;
  state.ready = new Promise((resolve) => {
    const host = document.createElement("div");
    host.id = "clause-privy";
    document.body.appendChild(host);
    createRoot(host).render(
      <PrivyProvider
        appId={appId}
        config={{
          loginMethods: ["email", "google", "passkey", "wallet"],
          appearance: {
            theme: theme === "light" ? "light" : "dark",
            accentColor: "#F5A524",
            landingHeader: "Sign in to Clause",
            showWalletLoginFirst: false,
            walletChainType: "ethereum-only",
          },
          embeddedWallets: {
            ethereum: { createOnLogin: "off" },
            solana: { createOnLogin: "off" },
          },
        }}
      >
        <Bridge onReady={resolve} />
      </PrivyProvider>
    );
  });
  return state.ready;
}

function login() {
  if (!state.api) return Promise.reject(new Error("not started"));
  if (state.api.authenticated) return state.api.getAccessToken();
  return new Promise((resolve, reject) => {
    state.pending = { resolve, reject };
    state.api.login();
  });
}

async function token() {
  if (!state.api || !state.api.authenticated) return null;
  try { return await state.api.getAccessToken(); } catch (e) { return null; }
}

async function logout() {
  if (state.api && state.api.authenticated) await state.api.logout();
}

function linkX() {
  if (!state.api) return Promise.reject(new Error("not started"));
  if (!state.api.authenticated) return Promise.reject(new Error("sign in first"));
  return new Promise((resolve, reject) => {
    state.linking = { resolve, reject };
    state.api.linkTwitter();
  });
}

async function identityToken() {
  if (!state.api || !state.api.authenticated) return null;
  try { return await getIdentityToken(); } catch (e) { return null; }
}

window.ClausePrivy = { start, login, token, logout, linkX, identityToken };
