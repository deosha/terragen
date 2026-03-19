"use client";

import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { FileCode } from "lucide-react";

interface CodePreviewProps {
  files: Record<string, string>;
  changes?: Record<string, { old: string; new: string }>;
}

export function CodePreview({ files, changes }: CodePreviewProps) {
  const fileNames = Object.keys(files);
  const [activeFile, setActiveFile] = useState(fileNames[0] || "");

  if (fileNames.length === 0) {
    return null;
  }

  return (
    <Card className="overflow-hidden bg-zinc-950">
      <Tabs value={activeFile} onValueChange={setActiveFile}>
        <div className="flex items-center border-b border-zinc-800 bg-zinc-900 px-2">
          <TabsList className="h-10 bg-transparent">
            {fileNames.map((name) => (
              <TabsTrigger
                key={name}
                value={name}
                className="gap-1.5 text-xs data-[state=active]:bg-zinc-950"
              >
                <FileCode className="h-3 w-3" />
                {name}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        {fileNames.map((name) => (
          <TabsContent key={name} value={name} className="m-0">
            <CardContent className="p-0">
              <pre className="max-h-[400px] overflow-auto p-4 text-xs">
                <code className="language-hcl text-zinc-300">
                  {changes && changes[name] ? (
                    <DiffView
                      oldCode={changes[name].old}
                      newCode={changes[name].new}
                    />
                  ) : (
                    <HighlightedCode code={files[name]} />
                  )}
                </code>
              </pre>
            </CardContent>
          </TabsContent>
        ))}
      </Tabs>
    </Card>
  );
}

function HighlightedCode({ code }: { code: string }) {
  // Simple syntax highlighting for HCL/Terraform
  const highlighted = code
    .split("\n")
    .map((line, i) => {
      let processed = line
        // Keywords
        .replace(
          /\b(resource|variable|output|provider|module|data|locals|terraform)\b/g,
          '<span class="text-purple-400">$1</span>'
        )
        // Strings
        .replace(
          /"([^"]*)"/g,
          '<span class="text-green-400">"$1"</span>'
        )
        // Comments
        .replace(
          /(#.*)$/g,
          '<span class="text-zinc-500">$1</span>'
        )
        // Booleans and numbers
        .replace(
          /\b(true|false|\d+)\b/g,
          '<span class="text-yellow-400">$1</span>'
        );

      return (
        <span key={i} className="block">
          <span className="mr-4 inline-block w-6 text-right text-zinc-600">
            {i + 1}
          </span>
          <span dangerouslySetInnerHTML={{ __html: processed }} />
        </span>
      );
    });

  return <>{highlighted}</>;
}

function DiffView({ oldCode, newCode }: { oldCode: string; newCode: string }) {
  const oldLines = oldCode.split("\n");
  const newLines = newCode.split("\n");

  // Simple line-by-line diff
  const maxLines = Math.max(oldLines.length, newLines.length);
  const diffLines = [];

  for (let i = 0; i < maxLines; i++) {
    const oldLine = oldLines[i] || "";
    const newLine = newLines[i] || "";

    if (oldLine === newLine) {
      diffLines.push({ type: "same", content: newLine, lineNum: i + 1 });
    } else if (!oldLine) {
      diffLines.push({ type: "add", content: newLine, lineNum: i + 1 });
    } else if (!newLine) {
      diffLines.push({ type: "remove", content: oldLine, lineNum: i + 1 });
    } else {
      diffLines.push({ type: "remove", content: oldLine, lineNum: i + 1 });
      diffLines.push({ type: "add", content: newLine, lineNum: i + 1 });
    }
  }

  return (
    <>
      {diffLines.map((line, i) => (
        <span
          key={i}
          className={`block ${
            line.type === "add"
              ? "bg-green-950 text-green-300"
              : line.type === "remove"
              ? "bg-red-950 text-red-300"
              : ""
          }`}
        >
          <span className="mr-2 inline-block w-4 text-zinc-600">
            {line.type === "add" ? "+" : line.type === "remove" ? "-" : " "}
          </span>
          <span className="mr-4 inline-block w-6 text-right text-zinc-600">
            {line.lineNum}
          </span>
          {line.content}
        </span>
      ))}
    </>
  );
}
