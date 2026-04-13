"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getAdminToken } from "@/lib/api";
import { Nav } from "@/components/Nav";
import { Toaster } from "@/components/ui/sonner";
import { Skeleton } from "@/components/ui/skeleton";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);


  useEffect(() => {
    if (pathname === "/login") {
      setReady(true);
      return;
    }
    if (!getAdminToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [pathname, router]);

  if (pathname === "/login") {
    return (
      <div className="min-h-screen bg-background">
        <Toaster theme="dark" />
        {children}
      </div>
    );
  }

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Toaster theme="dark" />
        <div className="w-64 space-y-3">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Toaster theme="dark" />
      <Nav />
      <main aria-label="Main content" className="flex-1 overflow-auto p-8">{children}</main>
    </div>
  );
}
