"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

const WARNING_TIME = 10 * 60 * 1000;
const LOGOUT_TIME = 15 * 60 * 1000;

export default function SessionTimeout() {
  const router = useRouter();

  const warningTimeout = useRef<NodeJS.Timeout | null>(null);
  const logoutTimeout = useRef<NodeJS.Timeout | null>(null);

  function clearTimers() {
    if (warningTimeout.current) {
      clearTimeout(warningTimeout.current);
    }

    if (logoutTimeout.current) {
      clearTimeout(logoutTimeout.current);
    }
  }

  function logout() {
    localStorage.removeItem("insyt_access_token");
    localStorage.removeItem("insyt_user");

    alert("Your INSYT session expired due to inactivity.");

    window.location.href = "/login";
  }

  function resetTimers() {
    clearTimers();

    warningTimeout.current = setTimeout(() => {
      alert("You will be logged out in 5 minutes due to inactivity.");
    }, WARNING_TIME);

    logoutTimeout.current = setTimeout(() => {
      logout();
    }, LOGOUT_TIME);
  }

  useEffect(() => {
    const events = [
      "mousemove",
      "mousedown",
      "keydown",
      "scroll",
      "touchstart",
    ];

    events.forEach((event) => {
      window.addEventListener(event, resetTimers);
    });

    resetTimers();

    return () => {
      clearTimers();

      events.forEach((event) => {
        window.removeEventListener(event, resetTimers);
      });
    };
  }, []);

  return null;
}