import type { Metadata } from "next";
import "./globals.css";
import Providers from "./providers";
import { AuthGate } from "@/components/AuthGate";

export const metadata: Metadata = {
  title: "Content OS",
  description: "Content Operating System Frontend",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full bg-canvas text-strong antialiased">
      <body className="min-h-full flex flex-col font-sans">
        <Providers><AuthGate>{children}</AuthGate></Providers>
      </body>
    </html>
  );
}

