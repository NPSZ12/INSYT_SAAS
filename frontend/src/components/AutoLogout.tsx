"use client";

import { useEffect, useRef, useState } from "react";

const AUTO_LOGOUT_MS = 20 * 60 * 1000;
const WARNING_MS = 15 * 60 * 1000;

export default function AutoLogout() {
  const logoutTimer = useRef<NodeJS.Timeout | null>(null);
  const warningTimer = useRef<NodeJS.Timeout | null>(null);

  const [showWarning, setShowWarning] = useState(false);

  function logout() {
    localStorage.removeItem("insyt_user");
    window.location.href = "/login";
  }

  function resetTimers() {
    setShowWarning(false);

    if (logoutTimer.current) clearTimeout(logoutTimer.current);
    if (warningTimer.current) clearTimeout(warningTimer.current);

    warningTimer.current = setTimeout(() => {
      setShowWarning(true);
    }, AUTO_LOGOUT_MS - WARNING_MS);

    logoutTimer.current = setTimeout(() => {
      logout();
    }, AUTO_LOGOUT_MS);
  }

  useEffect(() => {
    const events = [
      "mousemove",
      "mousedown",
      "keydown",
      "scroll",
      "touchstart",
      "click",
    ];

    resetTimers();

    events.forEach((event) => {
      window.addEventListener(event, resetTimers);
    });

    return () => {
      events.forEach((event) => {
        window.removeEventListener(event, resetTimers);
      });

      if (logoutTimer.current) clearTimeout(logoutTimer.current);
      if (warningTimer.current) clearTimeout(warningTimer.current);
    };
  }, []);

  if (!showWarning) return null;

  return (
    <div className="fixed inset-0 z-[9999] bg-black/70 flex items-center justify-center">
      <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
        <h2 className="text-xl font-bold text-white mb-3">
          Session Expiring Soon
        </h2>

        <p className="text-slate-300 mb-6">
          You will be logged out in 5 minutes due to inactivity.
        </p>

        <div className="flex gap-3 justify-end">
          <button
            type="button"
            onClick={logout}
            className="rounded-xl border border-slate-700 px-4 py-2 text-slate-300 hover:bg-slate-800"
          >
            Log Out Now
          </button>

          <button
            type="button"
            onClick={resetTimers}
            className="rounded-xl bg-sky-600 px-4 py-2 text-white hover:bg-sky-500"
          >
            Stay Logged In
          </button>
        </div>
      </div>
    </div>
  );
}