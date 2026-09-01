import { RECIPES, RECIPES_TITLE } from "@/lib/copy";

export default function RecipesPage() {
  return (
    <section className="mx-auto max-w-4xl px-4 py-16">
      <h1 className="text-4xl text-tomato sm:text-5xl">{RECIPES_TITLE}</h1>
      <ul className="mt-8 grid gap-4 sm:grid-cols-3">
        {RECIPES.map((recipe) => (
          <li
            key={recipe.name}
            className="ink-outline rounded-2xl bg-card p-5 transition-transform duration-200 hover:-translate-y-1"
          >
            <h2 className="text-xl text-foreground">{recipe.name}</h2>
            <p className="mt-2 text-sm font-semibold text-muted-foreground">
              {recipe.age} · {recipe.time}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
