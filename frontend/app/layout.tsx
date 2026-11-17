import type { Metadata } from "next";
import "./style.css";
import AppShell from "../components/app-shell";

export const metadata: Metadata = {
  title: "DENSO Prospecting",
  description: "Sales prospecting pilot",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" data-scroll-behavior="smooth"><body><AppShell>{children}</AppShell></body></html>;
}
