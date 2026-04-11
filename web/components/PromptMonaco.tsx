"use client";

import { useMemo } from "react";
import Editor from "@monaco-editor/react";

type Props = {
  value: string;
  onChange: (value: string) => void;
  height?: string;
  ariaLabel?: string;
};

export function PromptMonaco({ value, onChange, height = "320px", ariaLabel = "Prompt body editor" }: Props) {
  const options = useMemo(() => ({
    minimap: { enabled: false },
    wordWrap: "on" as const,
    fontSize: 13,
    scrollBeyondLastLine: false,
    padding: { top: 8, bottom: 8 },
  }), []);

  return (
    <div aria-label={ariaLabel}>
      <textarea
        className="sr-only"
        aria-label={ariaLabel}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <div className="overflow-hidden rounded-md border border-slate-700">
        <Editor
          height={height}
          theme="vs-dark"
          defaultLanguage="plaintext"
          value={value}
          onChange={(v) => onChange(v ?? "")}
          options={options}
        />
      </div>
    </div>
  );
}
