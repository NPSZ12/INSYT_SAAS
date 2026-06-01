"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ProjectsRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/projects?workspace=summaries");
  }, [router]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-400 flex items-center justify-center">
      Loading Projects...
    </div>
  );
}