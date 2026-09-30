import type { AppProps } from "next/app";
import { Inter } from "next/font/google";
import "@/app/globals.css";
import { SiteNav } from "@/components/site-nav";
import { cn } from "@/lib/utils";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export default function App({ Component, pageProps }: AppProps) {
  return (
    <div className={cn(inter.variable, "font-sans flex min-h-screen flex-col")}>
      <SiteNav />
      <Component {...pageProps} />
    </div>
  );
}
