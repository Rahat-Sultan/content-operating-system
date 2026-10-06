import type { Metadata } from "next";
import "./globals.css";
import Providers from "./providers";
import { Suspense } from "react";
import { AuthGate } from "@/components/AuthGate";
import { AppShell } from "@/components/AppShell";

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
        <Providers>
          <AuthGate>
            <Suspense fallback={null}>
              <AppShell>{children}</AppShell>
            </Suspense>
          </AuthGate>
        </Providers>
      </body>
    </html>
  );
}

