"use client";

import Editor from "@monaco-editor/react";

type Props = {
  value: string;
  onChange: (value: string) => void;
  height?: string;
};

export function PromptMonaco({ value, onChange, height = "320px" }: Props) {
  return (
    <div className="overflow-hidden rounded-md border border-slate-700">
      <Editor
        height={height}
        theme="vs-dark"
        defaultLanguage="plaintext"
        value={value}
        onChange={(v) => onChange(v ?? "")}
        options={{
          minimap: { enabled: false },
          wordWrap: "on",
          fontSize: 13,
          scrollBeyondLastLine: false,
          padding: { top: 8, bottom: 8 },
        }}
      />
    </div>
  );
}
