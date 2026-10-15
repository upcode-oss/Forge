import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import "@fontsource-variable/geist-mono";
import "@fontsource-variable/inter";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Upcode Forge", template: "%s · Upcode Forge" },
  description: "Self-hosted Git collaboration for your organization",
  icons: { icon: "/logo.png" },
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
