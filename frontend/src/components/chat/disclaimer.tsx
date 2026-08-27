import { DISCLAIMER_FALLBACK } from "@/lib/copy";

export function Disclaimer({ text }: { text: string | null }) {
  return (
    <p className="mt-3 border-t pt-2 text-xs leading-relaxed text-muted-foreground" role="note">
      {text ?? DISCLAIMER_FALLBACK}
    </p>
  );
}
