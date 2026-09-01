"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import frame1 from "@/assets/baby-chef-1.png";
import frame2 from "@/assets/baby-chef-2.png";
import frame3 from "@/assets/baby-chef-3.png";
import frame4 from "@/assets/baby-chef-4.png";
import { HERO_FLIPBOOK_HOVER_HINT, HERO_FLIPBOOK_PLAYING_HINT } from "@/lib/copy";

const frames = [
  {
    src: frame1,
    alt: "Cheerful cartoon baby chef waving beside a bowl of carrots and broccoli",
  },
  {
    src: frame2,
    alt: "Cartoon baby chef reaching into the bowl to pick up a carrot",
  },
  { src: frame3, alt: "Cartoon baby chef happily crunching on a carrot" },
  {
    src: frame4,
    alt: "Cartoon baby chef cheering with both hands up after finishing the veggies",
  },
];

// 6 second loop: frame 1, 2, 3 for one second each, then frame 4 for three seconds.
const timeline = [0, 1, 2, 3] as const;
const durations = [1000, 1000, 1000, 3000];

export function BabyChefFlipbook() {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!playing) return;
    timer.current = setTimeout(
      () => setIndex((i) => (i + 1) % timeline.length),
      durations[index] ?? 1000,
    );
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [playing, index]);

  const start = () => setPlaying(true);
  const stop = () => {
    setPlaying(false);
    setIndex(0);
  };

  return (
    <div
      className="relative mt-10 w-full max-w-xl"
      onMouseEnter={start}
      onMouseLeave={stop}
      onFocus={start}
      onBlur={stop}
      onTouchStart={start}
      tabIndex={0}
      role="img"
      aria-label={frames[index]?.alt ?? frames[0]!.alt}
    >
      <div
        className="absolute inset-x-6 bottom-4 top-6 rounded-[50%] bg-caramel/25 blur-2xl"
        aria-hidden="true"
      />
      <div className="animate-breathe relative overflow-hidden rounded-[2.5rem] border-[3px] border-ink bg-cream shadow-[6px_8px_0_var(--ink)]">
        {frames.map((frame, i) => (
          <Image
            key={frame.alt}
            src={frame.src}
            alt=""
            aria-hidden="true"
            className={`w-full transition-opacity duration-200 ${
              i === index ? "opacity-100" : "absolute inset-0 opacity-0"
            }`}
          />
        ))}
      </div>
      <p className="mt-3 text-center text-sm font-bold text-caramel">
        {playing ? HERO_FLIPBOOK_PLAYING_HINT : HERO_FLIPBOOK_HOVER_HINT}
      </p>
    </div>
  );
}
