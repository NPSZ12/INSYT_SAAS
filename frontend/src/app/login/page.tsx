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
  const [mfaCode, setMfaCode] = useState("");

  const [loginStage, setLoginStage] = useState<
    "password" | "mfa"
  >("password");

  const [errorMessage, setErrorMessage] = useState("");

  const [showAdminLogin, setShowAdminLogin] = useState(false);

  function finishLogin(response: any) {
    localStorage.setItem(
      "insyt_access_token",
      response.access_token
    );

    localStorage.setItem(
      "insyt_user",
      JSON.stringify(response.user)
    );

    window.location.href = nextPath;
  }

  function handleMicrosoftLogin() {
    setErrorMessage("");

    const postLoginRedirect =
      encodeURIComponent(nextPath || "/launcher");

    const isLocal =
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1";

    if (isLocal) {
      window.location.href =
        `https://www.insyt360.com/.auth/login/aad?post_login_redirect_uri=${postLoginRedirect}`;
      return;
    }

    window.location.href =
      `/.auth/login/aad?post_login_redirect_uri=${postLoginRedirect}`;
  }

  function handleLogin() {
    setErrorMessage("");

    apiPost("/api/auth/login", {
      username,
      password,
      mfa_code: loginStage === "mfa" ? mfaCode : "",
    })
      .then((response) => {
        if (response.status === "success") {
          finishLogin(response);
          return;
        }

        if (response.status === "mfa_required") {
          setLoginStage("mfa");
          setErrorMessage("");
          return;
        }

        if (response.status === "mfa_setup_required") {
          localStorage.setItem(
            "insyt_access_token",
            response.access_token
          );

          localStorage.setItem(
            "insyt_user",
            JSON.stringify(response.user)
          );

          window.location.href = "/mfa/setup";
          return;
        }

        setErrorMessage("Unable to complete sign in.");
      })
      .catch((error) => {
        console.error(error);

        if (loginStage === "mfa") {
          setErrorMessage("Invalid MFA code.");
        } else {
          setErrorMessage("Invalid username or password.");
        }
      });
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center">
      <div className="w-full max-w-md bg-slate-900 p-8 rounded-2xl shadow-xl border border-slate-800">
        <div className="flex items-end justify-center gap-0.5 mb-2">
          <span className="insyt-brand text-5xl font-bold text-white">
            I
          </span>

          <span className="insyt-brand text-5xl font-bold text-sky-400">
            N
          </span>

          <span className="insyt-brand text-5xl font-bold text-white">
            SYT
          </span>

          <span className="insyt-brand text-[2.1em] leading-none mb-[0.11em] text-sky-400 font-bold">
            360
          </span>
        </div>

        <p className="text-slate-400 text-center mb-8">
          Enterprise Review & Intelligence Platform
        </p>

        {!showAdminLogin ? (
          <>
            <Button
              fullWidth
              variant="primary"
              onClick={handleMicrosoftLogin}
            >
              Secure Sign In
            </Button>

            <button
              type="button"
              onClick={() => {
                setShowAdminLogin(true);
                setErrorMessage("");
              }}
              className="mt-5 w-full text-sm text-slate-400 hover:text-white"
            >
              INSYT Admin Login
            </button>
          </>
        ) : loginStage === "password" ? (
          <>
            <div className="mb-4">
              <Input
                placeholder="Username"
                value={username}
                onChange={setUsername}
              />
            </div>

            <div className="mb-6">
              <Input
                type="password"
                placeholder="Password"
                value={password}
                onChange={setPassword}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    handleLogin();
                  }
                }}
              />
            </div>

            <Button fullWidth onClick={handleLogin}>
              INSYT Admin Sign In
            </Button>

            <button
              type="button"
              onClick={() => {
                setShowAdminLogin(false);
                setLoginStage("password");
                setUsername("");
                setPassword("");
                setMfaCode("");
                setErrorMessage("");
              }}
              className="mt-4 w-full text-sm text-slate-400 hover:text-white"
            >
              Back to Microsoft Sign In
            </button>
          </>
        ) : (
          <>
            <div className="mb-3 rounded-xl border border-sky-800 bg-sky-950/40 p-4 text-sm text-sky-100">
              Enter the 6-digit code from your authenticator app.
            </div>

            <div className="mb-6">
              <Input
                placeholder="MFA Code"
                value={mfaCode}
                onChange={setMfaCode}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    handleLogin();
                  }
                }}
              />
            </div>

            <Button fullWidth onClick={handleLogin}>
              Verify MFA Code
            </Button>

            <button
              type="button"
              onClick={() => {
                setLoginStage("password");
                setMfaCode("");
                setErrorMessage("");
              }}
              className="mt-4 w-full text-sm text-slate-400 hover:text-white"
            >
              Back to Admin Login
            </button>
          </>
        )}

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