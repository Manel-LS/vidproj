"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Clapperboard } from "lucide-react";
import { useAuth } from "@/lib/auth";

/** Entry point: send signed-in users to their projects, everyone else to sign-in. */
export default function IndexPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/dashboard" : "/login");
  }, [user, loading, router]);

  return (
    <main className="flex min-h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-4 text-muted">
        <span className="flex h-11 w-11 animate-pulse items-center justify-center rounded-xl bg-accent">
          <Clapperboard className="h-6 w-6 text-white" aria-hidden />
        </span>
        <p className="text-sm">Loading Reelcraft…</p>
      </div>
    </main>
  );
}
