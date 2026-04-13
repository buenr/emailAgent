import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/api", "/_next", "/favicon.ico"];
const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

function loginRedirect(request: NextRequest) {
  const loginUrl = new URL("/login", request.url);
  const response = NextResponse.redirect(loginUrl);
  response.cookies.set("admin_token", "", { path: "/", maxAge: 0, sameSite: "strict" });
  return response;
}

async function tokenIsValid(request: NextRequest, token: string): Promise<boolean> {
  const base = API_BASE || request.nextUrl.origin;
  try {
    const res = await fetch(`${base}/api/auth/me`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );
  if (isPublic) return NextResponse.next();

  const token = request.cookies.get("admin_token")?.value;
  if (!token) return loginRedirect(request);

  const valid = await tokenIsValid(request, token);
  if (!valid) {
    return loginRedirect(request);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon\\.ico).*)"],
};
