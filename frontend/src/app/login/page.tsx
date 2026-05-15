"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import Button from "../../components/Button";
import Input from "../../components/Input";
import { apiPost } from "../../lib/api";

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = searchParams.get("next") || "/launcher";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  function handleLogin() {
    setErrorMessage("");

    apiPost("/api/auth/login", { username, password })
      .then((response) => {
        localStorage.setItem("insyt_access_token", response.access_token);
        localStorage.setItem("insyt_user", JSON.stringify(response.user));
        router.push(nextPath);
      })
      .catch(() => {
        setErrorMessage("Invalid username or password.");
      });
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center">
      <div className="w-full max-w-md bg-slate-900 p-8 rounded-2xl shadow-xl border border-slate-800">
        <h1 className="text-3xl font-bold mb-2 text-center">INSYT</h1>

        <p className="text-slate-400 text-center mb-8">
          Enterprise Review & Intelligence Platform
        </p>

        <div className="mb-4">
          <Input placeholder="Username" value={username} onChange={setUsername} />
        </div>

        <div className="mb-6">
          <Input type="password" placeholder="Password" value={password} onChange={setPassword} />
        </div>

        <Button fullWidth onClick={handleLogin}>
          Sign In
        </Button>

        {errorMessage && (
          <p className="text-red-400 text-sm mt-4 text-center">
            {errorMessage}
          </p>
        )}
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div>Loading login...</div>}>
      <LoginPageContent />
    </Suspense>
  );
}