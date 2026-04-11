"use client";

import { useEffect } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Results error:", error);
  }, [error]);

  return (
    <div className="flex items-center justify-center min-h-[60vh] p-4">
      <Card className="w-full max-w-md">
        <CardContent className="pt-6">
          <Alert variant="destructive">
            <AlertTitle>Failed to load results</AlertTitle>
            <AlertDescription>
              The results page could not be loaded. This may be a temporary
              issue.
              {error.digest && (
                <span className="block mt-1 text-xs opacity-70">
                  Error ID: {error.digest}
                </span>
              )}
            </AlertDescription>
          </Alert>
          <div className="mt-4 flex justify-end">
            <Button onClick={() => reset()} variant="outline">
              Try again
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
