import { redirect } from "next/navigation"

// The docs page is the landing page; the nav bar comes from pages/_app.tsx.
export default function Home() {
  redirect("/docs/page")
}
