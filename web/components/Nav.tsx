"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearAdminToken } from "@/lib/api";
import { Button } from "@/components/ui/button";

const links = [
  { href: "/dashboard", label: "Agents Dashboard" },
  {
    section: "Configuration", items: [
      { href: "/prompts", label: "Prompt Templates" },
      { href: "/classifications", label: "Classification Sets" },
      { href: "/models", label: "App Models" },
      { href: "/agent-apis", label: "Agent APIs" },
    ]
  },
  {
    section: "Workflow Builders", items: [
      { href: "/workflows/classification", label: "Classification Workflows" },
      { href: "/workflows/agentic", label: "Agentic Workflows" },
    ]
  },
  { href: "/results", label: "Results & Analytics" },
];

export function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  function signOut() {
    clearAdminToken();
    router.replace("/login");
  }

  return (
    <aside aria-label="Main navigation" className="w-64 shrink-0 border-r border-slate-800 bg-slate-900/80 p-6">
      <h1 className="mb-8 text-xs font-bold uppercase tracking-widest text-slate-500">
        Email Classifier
      </h1>
      <nav aria-label="Primary" className="flex flex-col gap-4">
        {links.map((link) => {
          if ("href" in link) {
            const isActive = link.href === "/" ? pathname === "/" : pathname === link.href || pathname.startsWith(link.href + "/");
            return (
              <Link
                key={link.href}
                href={link.href as string}
                aria-current={isActive ? "page" : undefined}
                className={
                  isActive
                    ? "rounded-md bg-slate-800 px-4 py-2.5 text-sm font-medium text-white transition-all"
                    : "rounded-md px-4 py-2.5 text-sm font-medium text-slate-400 transition-all hover:bg-slate-800/50 hover:text-slate-200"
                }
              >
                {link.label}
              </Link>
            );
          } else {
            return (
              <div key={link.section}>
                <p className="px-2 py-2 text-xs font-semibold uppercase tracking-widest text-slate-600">
                  {link.section}
                </p>
                <div className="space-y-1">
                  {link.items.map((item) => {
                    const isActive = item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(item.href + "/");
                    return (
                      <Link
                        key={item.href}
                        href={item.href as string}
                        aria-current={isActive ? "page" : undefined}
                        className={
                          isActive
                            ? "rounded-md bg-slate-800 px-4 py-2 text-xs font-medium text-white transition-all block"
                            : "rounded-md px-4 py-2 text-xs font-medium text-slate-400 transition-all hover:bg-slate-800/50 hover:text-slate-200 block"
                        }
                      >
                        {item.label}
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          }
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
