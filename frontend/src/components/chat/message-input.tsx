"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { INPUT_PLACEHOLDER, SEND, SENDING } from "@/lib/copy";

export function MessageInput({ onSend, disabled }: { onSend: (text: string) => void; disabled: boolean }) {
  const [value, setValue] = useState("");

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
  };

  return (
    <form
      className="flex items-end gap-2 border-t p-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder={INPUT_PLACEHOLDER}
        rows={2}
        maxLength={2000}
        aria-label={INPUT_PLACEHOLDER}
        className="min-h-0 resize-none"
      />
      <Button type="submit" disabled={disabled || value.trim() === ""}>
        {disabled ? SENDING : SEND}
      </Button>
    </form>
  );
}
