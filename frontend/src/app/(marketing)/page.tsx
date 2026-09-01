import { Carrot, HeartHandshake, Sparkles } from "lucide-react";
import Link from "next/link";
import { BabyChefFlipbook } from "@/components/marketing/baby-chef-flipbook";
import { FEATURES, FEATURES_TITLE, HERO_CTA, HERO_SUBCOPY, HERO_TITLE, SITE_TAGLINE } from "@/lib/copy";

const ICONS = [Carrot, Sparkles, HeartHandshake];

export default function MarketingHome() {
  return (
    <>
      <section className="paper-grain relative overflow-hidden">
        <div
          className="absolute inset-0"
          style={{ background: "var(--gradient-warm)" }}
          aria-hidden="true"
        />
        <div className="relative mx-auto flex max-w-4xl flex-col items-center px-4 py-16 text-center sm:py-24">
          <p className="ink-outline rounded-full bg-card px-4 py-1.5 text-sm font-bold tracking-wide text-caramel uppercase">
            {SITE_TAGLINE}
          </p>

          <h1 className="mt-6 text-4xl leading-tight text-tomato sm:text-6xl">{HERO_TITLE}</h1>

          <BabyChefFlipbook />

          <p className="mt-8 max-w-xl text-lg leading-relaxed text-foreground/80 sm:text-xl">
            {HERO_SUBCOPY}
          </p>

          <Link
            href="/app"
            className="ink-outline mt-8 rounded-full bg-primary px-8 py-4 text-lg font-bold text-primary-foreground transition-transform duration-200 hover:-translate-y-1 active:translate-y-0"
          >
            {HERO_CTA}
          </Link>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 py-16">
        <h2 className="text-center text-3xl text-foreground sm:text-4xl">{FEATURES_TITLE}</h2>
        <div className="mt-10 grid gap-6 sm:grid-cols-3">
          {FEATURES.map((feature, i) => {
            const Icon = ICONS[i]!;
            return (
              <article
                key={feature.title}
                className="ink-outline rounded-3xl bg-card p-6 text-center transition-transform duration-200 hover:-translate-y-1.5"
              >
                <span className="animate-wobble inline-flex size-14 items-center justify-center rounded-full border-[3px] border-ink bg-peach text-ink">
                  <Icon className="size-7" strokeWidth={2.5} aria-hidden="true" />
                </span>
                <h3 className="mt-4 text-xl text-tomato">{feature.title}</h3>
                <p className="mt-2 text-base leading-relaxed text-foreground/75">{feature.body}</p>
              </article>
            );
          })}
        </div>
      </section>
    </>
  );
}
