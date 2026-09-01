"use client";

import { ChefHat } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  NAV_ABOUT,
  NAV_CONTACT,
  NAV_HOME,
  NAV_LOGIN,
  NAV_RECIPES,
  SITE_WORDMARK,
} from "@/lib/copy";

const links = [
  { href: "/", label: NAV_HOME },
  { href: "/about", label: NAV_ABOUT },
  { href: "/recipes", label: NAV_RECIPES },
  { href: "/contact", label: NAV_CONTACT },
] as const;

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 border-b-[3px] border-ink bg-cream/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-3 px-4 py-3 sm:flex-row sm:justify-between">
        <Link href="/" className="group flex items-center gap-2">
          <span className="flex size-10 items-center justify-center rounded-full border-[3px] border-ink bg-card text-ink transition-transform duration-300 group-hover:-rotate-12">
            <ChefHat className="size-5" strokeWidth={2.5} />
          </span>
          <span className="font-display text-2xl leading-none text-tomato sm:text-3xl">
            {SITE_WORDMARK}
          </span>
        </Link>

        <nav
          aria-label="Main"
          className="flex flex-wrap items-center justify-center gap-1 rounded-full border-[3px] border-ink bg-secondary px-2 py-1.5 shadow-[3px_3px_0_var(--ink)]"
        >
          {links.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded-full px-3 py-1.5 text-sm font-semibold text-secondary-foreground transition-all duration-200 hover:-translate-y-0.5 hover:bg-card sm:text-base ${
                  active ? "bg-card text-tomato" : ""
                }`}
              >
                {link.label}
              </Link>
            );
          })}
          <Link
            href="/app"
            className={`ml-1 rounded-full border-[3px] border-ink bg-primary px-4 py-1.5 text-sm font-bold text-primary-foreground transition-transform duration-200 hover:-translate-y-0.5 active:translate-y-0 sm:text-base ${
              pathname === "/app" ? "brightness-95" : ""
            }`}
          >
            {NAV_LOGIN}
          </Link>
        </nav>
      </div>
    </header>
  );
}
