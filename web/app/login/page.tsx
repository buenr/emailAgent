"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  apiBaseUrl,
  apiPublicPost,
  getAdminToken,
  setAdminToken,
} from "@/lib/api";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";

type Health = {
  admin_auth_disabled?: boolean;
};

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [companyPassword, setCompanyPassword] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<1 | 2>(1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authDisabled, setAuthDisabled] = useState(false);

  useEffect(() => {
    if (getAdminToken()) {
      router.replace("/dashboard");
      return;
    }
    fetch(`${apiBaseUrl}/api/health`, { cache: "no-store" })
      .then((r) => r.json() as Promise<Health>)
      .then((h) => setAuthDisabled(Boolean(h.admin_auth_disabled)))
      .catch(() => setAuthDisabled(false));
  }, [router]);

  async function devBypass() {
    setError(null);
    setLoading(true);
    try {
      const res = (await apiPublicPost("/api/auth/verify", {
        email: "dev@local",
        company_password: "x",
        code: "0000",
      })) as { access_token: string };
      setAdminToken(res.access_token);
      document.cookie = "admin_token=" + res.access_token + "; path=/; SameSite=Strict";
      router.replace("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed");
    } finally {
      setLoading(false);
    }
  }

  async function requestCode(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await apiPublicPost("/api/auth/request-code", {
        email,
        company_password: companyPassword,
      });
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = (await apiPublicPost("/api/auth/verify", {
        email,
        company_password: companyPassword,
        code,
      })) as { access_token: string };
      setAdminToken(res.access_token);
      document.cookie = "admin_token=" + res.access_token + "; path=/; SameSite=Strict";
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl text-foreground">
            Email Classifier — Admin sign-in
          </CardTitle>
          <CardDescription className="text-muted-foreground">
            Use your allowlisted work email, company password, and the code sent
            to your inbox.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {authDisabled && (
            <Alert className="border-amber-900/60 bg-amber-950/40 text-amber-200">
              <AlertDescription className="text-amber-200">
                <p className="mb-3">
                  API has{" "}
                  <code className="text-amber-100">ADMIN_AUTH_DISABLED</code>{" "}
                  set (development only).
                </p>
                <Button
                  type="button"
                  onClick={devBypass}
                  disabled={loading}
                  className="bg-amber-700 text-white hover:bg-amber-600"
                  size="sm"
                >
                  Continue without auth
                </Button>
              </AlertDescription>
            </Alert>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {step === 1 ? (
            <form onSubmit={requestCode} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="login-email" className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Email
                </Label>
                <Input
                  id="login-email"
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(ev) => setEmail(ev.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="login-password" className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Company password
                </Label>
                <Input
                  id="login-password"
                  type="password"
                  autoComplete="current-password"
                  value={companyPassword}
                  onChange={(ev) => setCompanyPassword(ev.target.value)}
                  required
                />
              </div>
              <Button
                type="submit"
                disabled={loading}
                className="bg-sky-600 text-white hover:bg-sky-500"
              >
                {loading ? "Sending…" : "Send sign-in code"}
              </Button>
            </form>
          ) : (
            <form onSubmit={verify} className="flex flex-col gap-4">
              <p className="text-sm text-muted-foreground">
                Enter the code emailed to{" "}
                <strong className="text-slate-200">{email}</strong>.
              </p>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="login-code" className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Code
                </Label>
                <Input
                  id="login-code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(ev) => setCode(ev.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="login-password-confirm" className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Company password (again)
                </Label>
                <Input
                  id="login-password-confirm"
                  type="password"
                  value={companyPassword}
                  onChange={(ev) => setCompanyPassword(ev.target.value)}
                  required
                />
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setStep(1);
                    setCode("");
                    setError(null);
                  }}
                  className="flex-1"
                >
                  Back
                </Button>
                <Button
                  type="submit"
                  disabled={loading}
                  className="flex-1 bg-sky-600 text-white hover:bg-sky-500"
                >
                  {loading ? "Signing in…" : "Sign in"}
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
