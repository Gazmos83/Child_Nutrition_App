import { ABOUT_PARAGRAPHS, ABOUT_TITLE } from "@/lib/copy";

export default function AboutPage() {
  return (
    <section className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-4xl text-tomato sm:text-5xl">{ABOUT_TITLE}</h1>
      {ABOUT_PARAGRAPHS.map((paragraph, i) => (
        <p key={i} className={`${i === 0 ? "mt-6" : "mt-4"} text-lg leading-relaxed text-foreground/80`}>
          {paragraph}
        </p>
      ))}
    </section>
  );
}
