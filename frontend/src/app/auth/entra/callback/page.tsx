"use client";

import { useEffect, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "https://api.insyt360.com";

function getClaim(claims: any[], names: string[]) {
  return claims?.find((claim: any) =>
    names.includes(String(claim.typ || claim.name || "").toLowerCase())
  )?.val;
}

function extractEmailFromAuthMe(meData: any) {
  // Azure App Service Easy Auth usually returns an array:
  // [{ provider_name, user_id, user_claims, user_claims... }]
  if (Array.isArray(meData)) {
    const identity = meData[0];
    const claims = identity?.user_claims || identity?.claims || [];

    return (
      identity?.user_id ||
      getClaim(claims, [
        "preferred_username",
        "email",
        "emails",
        "upn",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
      ])
    );
  }

  // Static Web Apps-style shape, just in case
  const principal = meData?.clientPrincipal;
  const claims = principal?.claims || [];

  return (
    principal?.userDetails ||
    getClaim(claims, [
      "preferred_username",
      "email",
      "emails",
      "upn",
      "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
      "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
    ])
  );
}

export default function EntraCallbackPage() {
  const [message, setMessage] = useState("Completing secure login...");

  useEffect(() => {
    async function completeLogin() {
      try {
        const meResponse = await fetch("/.auth/me", {
          credentials: "include",
        });

        if (!meResponse.ok) {
          throw new Error("Unable to read Microsoft Entra session.");
        }

        const meData = await meResponse.json();
        console.log("Easy Auth /.auth/me:", meData);

        const email = extractEmailFromAuthMe(meData);

        if (!email) {
          throw new Error("Microsoft Entra login did not return an email.");
        }

        const loginResponse = await fetch(`${API_BASE}/api/auth/entra-login`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "include",
          body: JSON.stringify({
            email,
          }),
        });

        if (!loginResponse.ok) {
          const errorText = await loginResponse.text();
          throw new Error(errorText || "INSYT Entra login failed.");
        }

        const loginData = await loginResponse.json();

        localStorage.setItem("insyt_token", loginData.token);
        localStorage.setItem("insyt_user", JSON.stringify(loginData.user));

        window.location.href = "/launcher";
      } catch (error: any) {
        console.error("Secure login failed:", error);
        setMessage(error.message || "Secure login failed.");
      }
    }

    completeLogin();
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 text-white">
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-xl">
        <h1 className="text-xl font-semibold">INSYT Secure Login</h1>
        <p className="mt-3 text-sm text-slate-300">{message}</p>
      </div>
    </div>
  );
}