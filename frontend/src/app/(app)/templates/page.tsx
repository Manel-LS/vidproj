"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Clock, Images, LayoutTemplate, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { EmptyState, Notice } from "@/components/ui/Feedback";
import { StyleCard } from "@/components/styles/StyleCard";
import { api } from "@/lib/api/client";
import type { VideoStyleKey } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export default function TemplatesPage() {
  const router = useRouter();
  const [category, setCategory] = useState("all");
  const [style, setStyle] = useState<VideoStyleKey>("product_showcase");

  const templates = useQuery({ queryKey: ["templates"], queryFn: () => api.templates() });
  const styles = useQuery({ queryKey: ["styles"], queryFn: api.styles });

  const items = templates.data?.items ?? [];
  const categories = ["all", ...(templates.data?.categories ?? [])];
  const filtered = category === "all" ? items : items.filter((item) => item.category === category);

  return (
    <div className="mx-auto max-w-[1400px] px-5 py-8 lg:px-8">
      <header className="mb-7">
        <h1 className="text-2xl font-semibold tracking-tight">Templates</h1>
        <p className="mt-1 text-sm text-muted">
          A template is a scene blueprint — it decides how many beats your video has, how
          long each runs and where the text sits. Pick one and it fills with your images.
        </p>
      </header>

      <div className="mb-5 flex flex-wrap gap-1.5">
        {categories.map((entry) => (
          <button
            key={entry}
            type="button"
            onClick={() => setCategory(entry)}
            className={cn(
              "rounded-pill border px-3 py-1.5 text-xs transition-colors",
              category === entry
                ? "border-accent bg-accent/10 text-accent"
                : "border-line text-muted hover:border-accent/40 hover:text-ink",
            )}
          >
            {entry === "all" ? "All" : entry}
          </button>
        ))}
      </div>

      {templates.isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="skeleton h-48 rounded-card" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<LayoutTemplate className="h-6 w-6" />}
          title="No templates in this category"
          action={
            <Button variant="secondary" onClick={() => setCategory("all")}>
              Show all
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((template) => {
            const [from, to] = template.gradient;
            return (
              <article
                key={template.key}
                className="group flex flex-col overflow-hidden rounded-card border border-line bg-surface transition-colors hover:border-accent/40"
              >
                <div
                  className="relative flex h-32 items-end p-4"
                  style={{ background: `linear-gradient(140deg, ${from}, ${to})` }}
                >
                  <span className="absolute right-3 top-3 rounded-pill bg-black/35 px-2 py-0.5 text-2xs text-white backdrop-blur">
                    {template.category}
                  </span>
                  <h2 className="text-lg font-semibold text-white drop-shadow">{template.name}</h2>
                </div>

                <div className="flex flex-1 flex-col p-4">
                  <p className="text-sm leading-relaxed text-muted">{template.description}</p>

                  <dl className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-2xs text-faint">
                    <div className="flex items-center gap-1">
                      <Clock className="h-3 w-3" aria-hidden />
                      <dd>~{template.recommended_duration}s</dd>
                    </div>
                    <div className="flex items-center gap-1">
                      <Images className="h-3 w-3" aria-hidden />
                      <dd>
                        {template.min_images}–{template.max_images} images
                      </dd>
                    </div>
                    <div className="flex items-center gap-1">
                      <Sparkles className="h-3 w-3" aria-hidden />
                      <dd>{template.scene_count_hint} beats</dd>
                    </div>
                  </dl>

                  <Button
                    className="mt-4 w-full"
                    variant="secondary"
                    onClick={() =>
                      router.push(`/create?template=${template.key}&style=${template.style}`)
                    }
                  >
                    Use this template
                  </Button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <section className="mt-12">
        <h2 className="text-lg font-semibold tracking-tight">Styles</h2>
        <p className="mt-1 text-sm text-muted">
          A style is the look: pacing, camera moves, transitions and typography. Every
          template starts from one, and you can change it at any time.
        </p>

        {styles.isError ? (
          <Notice tone="danger" className="mt-4">
            Could not load the styles. Check that the backend is running.
          </Notice>
        ) : (
          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {(styles.data ?? []).map((preset) => (
              <StyleCard
                key={preset.key}
                preset={preset}
                selected={style === preset.key}
                onSelect={setStyle}
              />
            ))}
          </div>
        )}

        <Button className="mt-5" onClick={() => router.push(`/create?style=${style}`)}>
          Create a video in this style
        </Button>
      </section>
    </div>
  );
}
