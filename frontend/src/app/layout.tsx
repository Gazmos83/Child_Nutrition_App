import type { Metadata } from "next";
import { Baloo_2, Bowlby_One_SC, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const baloo = Baloo_2({
  variable: "--font-baloo",
  weight: ["400", "600", "700"],
  subsets: ["latin"],
});

const bowlby = Bowlby_One_SC({
  variable: "--font-bowlby",
  weight: "400",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Little Gourmant — Warm Nutrition for Little Eaters",
  description:
    "Grounded child-nutrition answers and meal plans for newborns through about four years. Not medical advice.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${baloo.variable} ${bowlby.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
