import Link from "next/link";
import { NAV_ABOUT, NAV_CONTACT, footerCopyright } from "@/lib/copy";

export function SiteFooter() {
  return (
    <footer className="border-t-[3px] border-ink bg-secondary">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-4 py-6 text-sm text-secondary-foreground sm:flex-row">
        <p>{footerCopyright(new Date().getFullYear())}</p>
        <div className="flex gap-4">
          <Link href="/about" className="font-semibold hover:text-tomato">
            {NAV_ABOUT}
          </Link>
          <Link href="/contact" className="font-semibold hover:text-tomato">
            {NAV_CONTACT}
          </Link>
        </div>
      </div>
    </footer>
  );
}
