import { Badge } from "@/components/ui/badge";
import type { Intent } from "@/lib/api-types";
import { INTENT_LABELS } from "@/lib/copy";

export function IntentChip({ intent }: { intent: Intent | null }) {
  if (!intent) return null;
  return (
    <Badge variant="secondary" data-testid="intent-chip" data-intent={intent}>
      {INTENT_LABELS[intent]}
    </Badge>
  );
}
