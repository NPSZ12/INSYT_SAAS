"use client";

import { useEffect, useRef, useState } from "react";
import { apiPost } from "../lib/api";

const REVIEWER_AUTO_LOGOUT_MS = 10 * 60 * 1000;
const REVIEWER_WARNING_MS = 5 * 60 * 1000;

const INSYT_ADMIN_AUTO_LOGOUT_MS = 20 * 60 * 1000;
const INSYT_ADMIN_WARNING_MS = 5 * 60 * 1000;

function getCurrentUserRole() {
  try {
    const rawUser = localStorage.getItem("insyt_user");

    if (!rawUser) return "";

    const user = JSON.parse(rawUser);

    return String(user.role || user.user_role || "").trim();
  } catch {
    return "";
  }
}

function isInsytAdmin() {
  return getCurrentUserRole().toLowerCase() === "insyt admin";
}

export default function AutoLogout() {
  const logoutTimer = useRef<NodeJS.Timeout | null>(null);
  const warningTimer = useRef<NodeJS.Timeout | null>(null);
  const isLoggingOut = useRef(false);

  const [showWarning, setShowWarning] = useState(false);

  async function logout(reason: "manual" | "inactivity_timeout" = "manual") {
    if (isLoggingOut.current) return;

    isLoggingOut.current = true;

    const adminUser = isInsytAdmin();

    if (!adminUser) {
      try {
        await apiPost("/api/reviewer-hours/logout", {
          logout_reason: reason,
          auto_logout_at: new Date().toISOString(),
        });
      } catch (error) {
        console.error("Failed to record reviewer hours logout", error);
      }
    }

    localStorage.removeItem("insyt_user");
    localStorage.removeItem("insyt_token");

    window.location.href = "/login";
  }

  function resetTimers() {
    if (isLoggingOut.current) return;

    setShowWarning(false);

    if (logoutTimer.current) clearTimeout(logoutTimer.current);
    if (warningTimer.current) clearTimeout(warningTimer.current);

    const adminUser = isInsytAdmin();

    const autoLogoutMs = adminUser
      ? INSYT_ADMIN_AUTO_LOGOUT_MS
      : REVIEWER_AUTO_LOGOUT_MS;

    const warningMs = adminUser
      ? INSYT_ADMIN_WARNING_MS
      : REVIEWER_WARNING_MS;

    warningTimer.current = setTimeout(() => {
      setShowWarning(true);
    }, autoLogoutMs - warningMs);

    logoutTimer.current = setTimeout(() => {
      logout("inactivity_timeout");
    }, autoLogoutMs);
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

  const adminUser = isInsytAdmin();

  return (
    <div className="fixed inset-0 z-[9999] bg-black/70 flex items-center justify-center">
      <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
        <h2 className="text-xl font-bold text-white mb-3">
          Session Expiring Soon
        </h2>

        <p className="text-slate-300 mb-6">
          {adminUser
            ? "You will be logged out in 5 minutes due to inactivity."
            : "You will be logged out in 5 minutes due to inactivity. Inactive time will not be added to Reviewer Hours."}
        </p>

        <div className="flex gap-3 justify-end">
          <button
            type="button"
            onClick={() => logout("manual")}
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