"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function UserAccessRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/user-access?workspace=discovery");
  }, [router]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-400 flex items-center justify-center">
      Loading User Access...
    </div>
  );
}