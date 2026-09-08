"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Clapperboard, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Feedback";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth";

const DEMO_EMAIL = "demo@reelcraft.app";
const DEMO_PASSWORD = "demo1234";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const { user, loading: restoring, signIn, signUp } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (user) router.replace("/dashboard");
  }, [user, router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (mode === "login") await signIn(email, password);
      else await signUp(email, password, fullName);
      router.replace("/dashboard");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Could not reach the server. Check that the backend is running.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function signInAsDemo() {
    setError("");
    setSubmitting(true);
    try {
      await signIn(DEMO_EMAIL, DEMO_PASSWORD);
      router.replace("/dashboard");
    } catch {
      setError(
        "The demo account is not set up. Run `python -m app.seed` in the backend to create it.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const isRegister = mode === "register";

  return (
    <main id="main" className="grid min-h-screen lg:grid-cols-2">
      {/* Left: the pitch. Hidden on small screens so the form gets the space. */}
      <section className="relative hidden overflow-hidden border-r border-line bg-surface lg:block">
        <div
          className="absolute inset-0 opacity-40"
          style={{
            background:
              "radial-gradient(120% 90% at 15% 5%, rgb(124 108 255 / 0.35), transparent 55%), radial-gradient(90% 70% at 90% 95%, rgb(236 72 153 / 0.28), transparent 60%)",
          }}
          aria-hidden
        />
        <div className="relative flex h-full flex-col justify-between p-12">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent">
              <Clapperboard className="h-5 w-5 text-white" aria-hidden />
            </span>
            <span className="text-lg font-semibold tracking-tight">Reelcraft</span>
          </div>

          <div className="max-w-md">
            <h1 className="text-balance text-4xl font-semibold leading-[1.1] tracking-tight">
              Your product photos, cut into a video people actually watch.
            </h1>
            <p className="mt-5 text-[15px] leading-relaxed text-muted">
              Upload a handful of images. Reelcraft plans the scenes, animates each shot,
              writes the captions and renders a 1080&nbsp;×&nbsp;1920 MP4 ready for TikTok,
              Reels and Shorts.
            </p>
            <ul className="mt-8 space-y-3 text-sm text-muted">
              {[
                "Cinematic zoom, pan and Ken Burns motion on every still",
                "Ten styles, from luxury slow-burn to TikTok whip-cuts",
                "Real FFmpeg rendering — download the MP4, no watermark",
              ].map((item) => (
                <li key={item} className="flex items-start gap-2.5">
                  <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <p className="text-xs text-faint">
            Rendering runs on your own infrastructure. AI features are optional and
            configured with your own API keys.
          </p>
        </div>
      </section>

      {/* Right: the form. */}
      <section className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent">
              <Clapperboard className="h-5 w-5 text-white" aria-hidden />
            </span>
            <span className="text-lg font-semibold tracking-tight">Reelcraft</span>
          </div>

          <h2 className="text-2xl font-semibold tracking-tight">
            {isRegister ? "Create your account" : "Welcome back"}
          </h2>
          <p className="mt-1.5 text-sm text-muted">
            {isRegister
              ? "Start turning photos into short-form video."
              : "Sign in to pick up where you left off."}
          </p>

          {error ? (
            <Notice tone="danger" className="mt-6">
              {error}
            </Notice>
          ) : null}

          <form onSubmit={submit} className="mt-6 space-y-4">
            {isRegister ? (
              <Input
                label="Your name"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Alex Rivera"
                autoComplete="name"
                maxLength={120}
              />
            ) : null}

            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
              autoComplete="email"
              required
            />

            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={isRegister ? "At least 8 characters" : "••••••••"}
              autoComplete={isRegister ? "new-password" : "current-password"}
              minLength={isRegister ? 8 : undefined}
              required
              hint={isRegister ? "Use at least 8 characters." : undefined}
            />

            {/* `restoring` disables the button while the stored session is checked,
                but must not show a spinner — on a fresh load there is nothing to wait
                for and a spinning button reads as a stuck page. */}
            <Button type="submit" size="lg" className="w-full" loading={submitting} disabled={restoring}>
              {isRegister ? "Create account" : "Sign in"}
            </Button>
          </form>

          <div className="my-6 flex items-center gap-3 text-2xs uppercase tracking-wider text-faint">
            <span className="h-px flex-1 bg-line" />
            or
            <span className="h-px flex-1 bg-line" />
          </div>

          <Button variant="secondary" className="w-full" onClick={signInAsDemo} disabled={submitting}>
            Try the demo account
          </Button>

          <p className="mt-6 text-center text-sm text-muted">
            {isRegister ? "Already have an account? " : "New here? "}
            <Link
              href={isRegister ? "/login" : "/register"}
              className="font-medium text-accent hover:underline"
            >
              {isRegister ? "Sign in" : "Create an account"}
            </Link>
          </p>
        </div>
      </section>
    </main>
  );
}
