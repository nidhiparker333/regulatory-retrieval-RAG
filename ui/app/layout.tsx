import type { Metadata } from "next";
import { Instrument_Serif, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

/**
 * Three faces, each doing a different job.
 *
 * The answer is set in a serif because it is prose meant to be read and
 * weighed. The trace is set in mono because it is instrumentation. Setting
 * both in one face would flatten the distinction this whole layout exists to
 * make.
 */
const display = Instrument_Serif({
  variable: "--font-display",
  subsets: ["latin"],
  weight: "400",
});

const sans = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

const mono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Governance RAG",
  description:
    "Grounded answers across the documents that govern AI, with the retrieval that produced each one shown alongside it.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${sans.variable} ${mono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-void text-ink">{children}</body>
    </html>
  );
}
