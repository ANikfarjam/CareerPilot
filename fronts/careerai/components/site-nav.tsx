"use client"

import Image from "next/image"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { BookOpen, Search } from "lucide-react"

import logo from "@/assests/Logo.jpeg"
import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
  navigationMenuTriggerStyle,
} from "@/components/ui/navigation-menu"
import { cn } from "@/lib/utils"

// One entry per route under pages/; add new pages here to show them in the nav.
const NAV_ITEMS = [
  { href: "/search/page", label: "Search", icon: Search },
  { href: "/docs/page", label: "Docs", icon: BookOpen },
]

// Top navigation bar shown on every pages/ route (rendered in _app.tsx).
export function SiteNav() {
  const pathname = usePathname()

  return (
    <header className="sticky top-0 z-20 border-b border-border/60 bg-background/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-4 sm:px-6">
        <Link href="/docs/page" className="flex items-center gap-3">
          <Image
            src={logo}
            alt="CareerAI"
            priority
            className="size-10 rounded-xl object-cover ring-1 ring-white/10"
          />
          <span className="bg-linear-to-r from-brand-blue via-brand-teal to-brand-green bg-clip-text text-lg font-semibold tracking-tight text-transparent">
            CareerAI
          </span>
        </Link>

        <NavigationMenu align="end">
          <NavigationMenuList className="gap-1">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
              const isActive = pathname === href
              return (
                <NavigationMenuItem key={href}>
                  <NavigationMenuLink
                    active={isActive}
                    render={<Link href={href} />}
                    className={cn(
                      navigationMenuTriggerStyle(),
                      "gap-2",
                      isActive ? "text-brand-teal" : "text-muted-foreground",
                    )}
                  >
                    <Icon />
                    {label}
                  </NavigationMenuLink>
                </NavigationMenuItem>
              )
            })}
          </NavigationMenuList>
        </NavigationMenu>
      </div>
    </header>
  )
}
