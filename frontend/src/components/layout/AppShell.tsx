"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import {
  Clapperboard,
  FolderOpen,
  Images,
  LayoutTemplate,
  LogOut,
  Menu,
  Plus,
  Settings,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Feedback";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Projects", icon: FolderOpen },
  { href: "/templates", label: "Templates", icon: LayoutTemplate },
  { href: "/media", label: "Media", icon: Images },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

/**
 * The signed-in shell.
 *
 * The editor route opts out of the sidebar entirely — it needs the full width for
 * the preview, timeline and property panels.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, signOut } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isEditor = pathname?.startsWith("/editor");

  // The drawer closes when a destination is chosen. Doing it here rather than in an
  // effect keyed on the pathname avoids a second render pass on every navigation.
  const closeMobile = () => setMobileOpen(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Loading your workspace…" />
      </div>
    );
  }

  if (!user) return null;

  if (isEditor) {
    return (
      <div id="main" className="min-h-screen">
        {children}
      </div>
    );
  }

  const initials =
    (user.full_name || user.email)
      .split(/[\s@.]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "U";

  const sidebar = (
    <div className="flex h-full flex-col">
      <Link
        href="/dashboard"
        className="flex items-center gap-2.5 px-5 py-5"
        onClick={closeMobile}
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent">
          <Clapperboard className="h-[18px] w-[18px] text-white" aria-hidden />
        </span>
        <span className="text-[15px] font-semibold tracking-tight">Reelcraft</span>
      </Link>

      <div className="px-3 pb-4">
        <Button
          className="w-full"
          icon={<Plus className="h-4 w-4" />}
          onClick={() => {
            closeMobile();
            router.push("/create");
          }}
        >
          Create Video
        </Button>
      </div>

      <nav className="flex-1 space-y-0.5 px-3" aria-label="Main">
        {NAV.map((item) => {
          const active = pathname === item.href || pathname?.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={closeMobile}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-elevated font-medium text-ink"
                  : "text-muted hover:bg-elevated/60 hover:text-ink",
              )}
            >
              <Icon className="h-[18px] w-[18px]" aria-hidden />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-line p-3">
        <div className="flex items-center gap-2.5 rounded-lg px-2 py-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-ink">
            {initials}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm text-ink">{user.full_name || "Creator"}</span>
            <span className="block truncate text-xs text-faint">{user.email}</span>
          </span>
          <Button variant="ghost" size="icon" onClick={signOut} aria-label="Sign out">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 hidden w-60 border-r border-line bg-surface lg:block">
        {sidebar}
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} aria-hidden />
          <aside className="relative h-full w-64 border-r border-line bg-surface">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute right-3 top-4 rounded-lg p-1.5 text-muted hover:text-ink"
              aria-label="Close navigation"
            >
              <X className="h-4 w-4" />
            </button>
            {sidebar}
          </aside>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col lg:pl-60">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-canvas/85 px-4 backdrop-blur lg:hidden">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu className="h-5 w-5" />
          </Button>
          <span className="text-sm font-semibold">Reelcraft</span>
        </header>

        <main id="main" className="min-w-0 flex-1">
          {children}
        </main>
      </div>
    </div>
  );
}
