import type { Metadata } from "next";
import "./style.css";
import AppShell from "../components/app-shell";
import { AuthProvider } from "../lib/auth-context";

export const metadata: Metadata = {
  title: "Solwer GTM | Enterprise Sales Intelligence Platform",
  description: "Evidence-grounded sales prospecting and autonomous automotive intelligence",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
