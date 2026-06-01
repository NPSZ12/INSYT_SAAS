"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { apiPost } from "../../../../lib/api";

function EntraCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [message, setMessage] = useState(
    "Completing Microsoft sign in..."
  );

  useEffect(() => {
    const code = searchParams.get("code");
    const error = searchParams.get("error");

    if (error) {
      setMessage("Microsoft sign in failed.");
      return;
    }

    if (!code) {
      setMessage("Missing Microsoft authorization code.");
      return;
    }

    apiPost("/api/auth/entra/callback", { code })
      .then((response) => {
        localStorage.setItem(
          "insyt_access_token",
          response.access_token
        );

        localStorage.setItem(
          "insyt_user",
          JSON.stringify(response.user)
        );

        window.location.href = "/launcher";
      })
      .catch((error) => {
        console.error(error);
        setMessage("Unable to complete Microsoft sign in.");
      });
  }, [searchParams, router]);

  return (
    <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center">
      <div className="w-full max-w-md bg-slate-900 p-8 rounded-2xl shadow-xl border border-slate-800 text-center">
        <h1 className="text-2xl font-bold mb-4">
          INSYT360
        </h1>

        <p className="text-slate-400">
          {message}
        </p>
      </div>
    </main>
  );
}

export default function EntraCallbackPage() {
  return (
    <Suspense fallback={<div>Completing sign in...</div>}>
      <EntraCallbackContent />
    </Suspense>
  );
}