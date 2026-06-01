"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import Button from "../../../components/Button";
import Input from "../../../components/Input";
import { apiPost } from "../../../lib/api";

export default function MfaSetupPage() {
  const router = useRouter();

  const [qrCode, setQrCode] = useState("");
  const [manualKey, setManualKey] = useState("");
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    apiPost("/api/auth/mfa/setup", {})
      .then((response) => {
        setQrCode(response.qr_code || "");
        setManualKey(response.manual_key || "");
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to start MFA setup.");
      });
  }, []);

  function confirmMfa() {
    setMessage("");

    apiPost("/api/auth/mfa/confirm", {
      code,
    })
      .then(() => {
        setMessage("MFA enabled.");

        setTimeout(() => {
          router.push("/launcher");
        }, 500);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Invalid MFA code.");
      });
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center p-6">
      <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl p-8">
        <h1 className="text-2xl font-bold mb-2">
          Set Up MFA
        </h1>

        <p className="text-slate-400 mb-6">
          INSYT Admin accounts require an authenticator app.
          Scan the QR code with Microsoft Authenticator,
          Google Authenticator, or Authy.
        </p>

        {qrCode ? (
          <div className="flex justify-center mb-6">
            <img
              src={qrCode}
              alt="MFA QR Code"
              className="rounded-xl bg-white p-4"
            />
          </div>
        ) : (
          <div className="mb-6 rounded-xl border border-slate-800 bg-slate-950 p-4 text-slate-400">
            Loading QR code...
          </div>
        )}

        {manualKey && (
          <div className="mb-6 rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-slate-500 mb-2">
              Manual Setup Key
            </div>

            <div className="break-all font-mono text-sm text-sky-300">
              {manualKey}
            </div>
          </div>
        )}

        <div className="mb-6">
          <Input
            placeholder="Enter 6-digit code"
            value={code}
            onChange={setCode}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                confirmMfa();
              }
            }}
          />
        </div>

        <Button fullWidth onClick={confirmMfa}>
          Confirm and Enable MFA
        </Button>

        {message && (
          <p className="mt-4 text-sm text-sky-400 text-center">
            {message}
          </p>
        )}
      </div>
    </main>
  );
}