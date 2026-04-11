"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearAdminToken } from "@/lib/api";
import { Button } from "@/components/ui/button";

const links = [
  { href: "/dashboard", label: "Fleet Dashboard" },
  { href: "/prompts", label: "Prompt Templates" },
  { href: "/classifications", label: "Classification Sets" },
  { href: "/models", label: "App models" },
  { href: "/inboxes", label: "Inboxes" },
  { href: "/results", label: "Results" },
];

export function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  function signOut() {
    clearAdminToken();
    router.replace("/login");
  }

  return (
    <aside className="w-64 shrink-0 border-r border-slate-800 bg-slate-900/80 p-6">
      <h1 className="mb-8 text-xs font-bold uppercase tracking-widest text-slate-500">
        Email Classifier
      </h1>
      <nav className="flex flex-col gap-2">
        {links.map(({ href, label }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={
                isActive
                  ? "rounded-md bg-slate-800 px-4 py-2.5 text-sm font-medium text-white transition-all"
                  : "rounded-md px-4 py-2.5 text-sm font-medium text-slate-400 transition-all hover:bg-slate-800/50 hover:text-slate-200"
              }
            >
              {label}
            </Link>
          );
        })}
        <Button
          variant="ghost"
          onClick={signOut}
          className="mt-4 justify-start px-4 py-2.5 text-sm font-medium text-slate-500 hover:bg-slate-800 hover:text-slate-300"
        >
          Sign out
        </Button>
      </nav>
    </aside>
  );
}
