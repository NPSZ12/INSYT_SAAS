"use client";

import { useEffect, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "https://api.insyt360.com";

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

        const identity =
          Array.isArray(meData)
            ? meData[0]
            : null;

        const idToken =
          identity?.id_token;

        if (!idToken) {
          throw new Error(
            "Microsoft Entra login did not return an identity token."
          );
        }

        const loginResponse = await fetch(
          `${API_BASE}/api/auth/entra-verified-login`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            credentials: "include",
            body: JSON.stringify({
              id_token: idToken,
            }),
          }
        );

        if (!loginResponse.ok) {
          const errorText = await loginResponse.text();
          throw new Error(errorText || "INSYT Entra login failed.");
        }

        const loginData = await loginResponse.json();

        const token =
          loginData.access_token ||
          loginData.token;

        if (!token) {
          throw new Error("INSYT login did not return a token.");
        }

        localStorage.setItem("insyt_token", token);
        localStorage.setItem("insyt_access_token", token);
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