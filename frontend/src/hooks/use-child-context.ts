"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";
import {
  EMPTY_CHILD_FORM,
  getChildFormSnapshot,
  parseChildForm,
  subscribeChildForm,
  toChildContext,
  writeChildForm,
  type ChildForm,
} from "@/lib/child-context-store";

const serverSnapshot = () => null;
const clientReady = () => true;
const serverReady = () => false;

/** Form state backed by localStorage as an external store; the server renders it empty. */
export function useChildContext() {
  const raw = useSyncExternalStore(subscribeChildForm, getChildFormSnapshot, serverSnapshot);
  const hydrated = useSyncExternalStore(subscribeChildForm, clientReady, serverReady);
  const form = useMemo(() => parseChildForm(raw) ?? EMPTY_CHILD_FORM, [raw]);

  const update = useCallback(
    <K extends keyof ChildForm>(key: K, value: ChildForm[K]) => {
      writeChildForm({ ...form, [key]: value });
    },
    [form],
  );

  const clear = useCallback(() => writeChildForm(null), []);

  const result = useMemo(() => toChildContext(form), [form]);
  return { form, update, clear, hydrated, ...result };
}
