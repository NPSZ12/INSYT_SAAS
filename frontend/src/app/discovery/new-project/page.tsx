"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function DiscoveryNewProjectRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/new-project?workspace=discovery");
  }, [router]);

  return (
    <div className="min-h-screen bg-slate-950 p-8 text-slate-300">
      Redirecting to global project creation...
    </div>
  );
}