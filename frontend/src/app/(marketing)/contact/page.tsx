"use client";

import {
  CONTACT_EMAIL_PLACEHOLDER,
  CONTACT_INTRO,
  CONTACT_MESSAGE_PLACEHOLDER,
  CONTACT_NAME_PLACEHOLDER,
  CONTACT_SUBMIT,
  CONTACT_TITLE,
} from "@/lib/copy";

export default function ContactPage() {
  return (
    <section className="mx-auto max-w-xl px-4 py-16">
      <h1 className="text-4xl text-tomato sm:text-5xl">{CONTACT_TITLE}</h1>
      <p className="mt-4 text-lg text-foreground/80">{CONTACT_INTRO}</p>
      <form className="mt-8 space-y-4" onSubmit={(event) => event.preventDefault()}>
        <input
          type="text"
          placeholder={CONTACT_NAME_PLACEHOLDER}
          className="ink-outline w-full rounded-2xl bg-card px-4 py-3 outline-none focus:ring-2 focus:ring-ring"
        />
        <input
          type="email"
          placeholder={CONTACT_EMAIL_PLACEHOLDER}
          className="ink-outline w-full rounded-2xl bg-card px-4 py-3 outline-none focus:ring-2 focus:ring-ring"
        />
        <textarea
          rows={4}
          placeholder={CONTACT_MESSAGE_PLACEHOLDER}
          className="ink-outline w-full rounded-2xl bg-card px-4 py-3 outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          type="submit"
          className="ink-outline rounded-full bg-primary px-6 py-3 font-bold text-primary-foreground transition-transform duration-200 hover:-translate-y-1 active:translate-y-0"
        >
          {CONTACT_SUBMIT}
        </button>
      </form>
    </section>
  );
}
