"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import Editor, { OnMount, OnChange } from "@monaco-editor/react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileCode,
  Save,
  RotateCcw,
  Loader2,
  Circle,
  AlertCircle,
  Pencil,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface CodeEditorProps {
  files: Record<string, string>;
  onSave?: (files: Record<string, string>) => Promise<void>;
  readOnly?: boolean;
}

export function CodeEditor({
  files,
  onSave,
  readOnly = false,
}: CodeEditorProps) {
  // Get file extension priority for sorting
  const getFilePriority = (name: string): number => {
    if (name === "main.tf") return 0;
    if (name.endsWith(".tf")) return 1;
    if (name.endsWith(".tfvars")) return 2;
    if (name.endsWith(".md")) return 3;
    if (name.endsWith(".yml") || name.endsWith(".yaml")) return 4;
    if (name.endsWith(".json")) return 5;
    return 6;
  };

  // Get Monaco language based on file extension
  const getLanguage = (fileName: string): string => {
    if (fileName.endsWith(".tf") || fileName.endsWith(".tfvars")) return "hcl";
    if (fileName.endsWith(".md")) return "markdown";
    if (fileName.endsWith(".json")) return "json";
    if (fileName.endsWith(".yml") || fileName.endsWith(".yaml")) return "yaml";
    return "plaintext";
  };

  const fileNames = Object.keys(files).sort((a, b) => {
    const priorityA = getFilePriority(a);
    const priorityB = getFilePriority(b);
    if (priorityA !== priorityB) return priorityA - priorityB;
    return a.localeCompare(b);
  });

  const [activeFile, setActiveFile] = useState(fileNames[0] || "");
  const [editedFiles, setEditedFiles] = useState<Record<string, string>>({ ...files });
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);

  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);

  // Track which files have been modified
  const modifiedFiles = useRef<Set<string>>(new Set());

  // Update editedFiles when external files change (e.g., after generation)
  useEffect(() => {
    setEditedFiles({ ...files });
    modifiedFiles.current.clear();
    setHasUnsavedChanges(false);
  }, [files]);

  const handleEditorMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;

    // Register HCL/Terraform language configuration
    monaco.languages.register({ id: "hcl" });

    monaco.languages.setMonarchTokensProvider("hcl", {
      tokenizer: {
        root: [
          // Comments
          [/#.*$/, "comment"],
          [/\/\/.*$/, "comment"],
          [/\/\*/, "comment", "@comment"],

          // Keywords
          [
            /\b(resource|variable|output|provider|module|data|locals|terraform|backend|required_providers|source|version)\b/,
            "keyword",
          ],

          // Booleans
          [/\b(true|false|null)\b/, "constant"],

          // Numbers
          [/\b\d+\.?\d*\b/, "number"],

          // Strings
          [/"/, "string", "@string_double"],
          [/'/, "string", "@string_single"],

          // Identifiers
          [/[a-zA-Z_][\w]*/, "identifier"],

          // Operators
          [/[={}()\[\],]/, "delimiter"],
        ],

        comment: [
          [/[^/*]+/, "comment"],
          [/\*\//, "comment", "@pop"],
          [/[/*]/, "comment"],
        ],

        string_double: [
          [/[^"\\$]+/, "string"],
          [/\$\{/, "string.interpolated", "@interpolation"],
          [/\\./, "string.escape"],
          [/"/, "string", "@pop"],
        ],

        string_single: [
          [/[^'\\]+/, "string"],
          [/\\./, "string.escape"],
          [/'/, "string", "@pop"],
        ],

        interpolation: [
          [/\}/, "string.interpolated", "@pop"],
          [/[^}]+/, "string.interpolated"],
        ],
      },
    });

    // Define theme
    monaco.editor.defineTheme("terraform-dark", {
      base: "vs-dark",
      inherit: true,
      rules: [
        { token: "keyword", foreground: "c586c0" },
        { token: "string", foreground: "ce9178" },
        { token: "string.interpolated", foreground: "9cdcfe" },
        { token: "string.escape", foreground: "d7ba7d" },
        { token: "number", foreground: "b5cea8" },
        { token: "constant", foreground: "569cd6" },
        { token: "comment", foreground: "6a9955" },
        { token: "identifier", foreground: "9cdcfe" },
        { token: "delimiter", foreground: "d4d4d4" },
      ],
      colors: {
        "editor.background": "#0a0a0a",
        "editor.foreground": "#d4d4d4",
        "editorLineNumber.foreground": "#5a5a5a",
        "editorLineNumber.activeForeground": "#c6c6c6",
        "editor.selectionBackground": "#264f78",
        "editor.lineHighlightBackground": "#1a1a1a",
      },
    });

    monaco.editor.setTheme("terraform-dark");
  };

  const handleEditorChange: OnChange = useCallback(
    (value) => {
      // Only track changes when in edit mode
      if (value !== undefined && activeFile && isEditing) {
        // Check if the value actually changed from the original
        if (value !== files[activeFile]) {
          setEditedFiles((prev) => ({
            ...prev,
            [activeFile]: value,
          }));
          modifiedFiles.current.add(activeFile);
          setHasUnsavedChanges(true);
          setSaveError(null);
        }
      }
    },
    [activeFile, isEditing, files]
  );

  const handleSave = async () => {
    if (!onSave || !hasUnsavedChanges) return;

    setIsSaving(true);
    setSaveError(null);

    try {
      await onSave(editedFiles);
      modifiedFiles.current.clear();
      setHasUnsavedChanges(false);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Save failed");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDiscard = () => {
    setEditedFiles({ ...files });
    modifiedFiles.current.clear();
    setHasUnsavedChanges(false);
    setSaveError(null);
  };


  const isFileModified = (fileName: string) => modifiedFiles.current.has(fileName);

  if (fileNames.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-lg border bg-zinc-950 p-8 text-zinc-500">
        No files to display
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950 overflow-hidden">
      {/* File Tabs */}
      <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900">
        <div className="flex-1 overflow-x-auto scrollbar-thin" style={{ maxWidth: 'calc(100% - 120px)' }}>
          <Tabs value={activeFile} onValueChange={setActiveFile}>
            <TabsList className="h-10 bg-transparent rounded-none border-0 flex w-max">
              {fileNames.map((name) => (
                <TabsTrigger
                  key={name}
                  value={name}
                  className="gap-1.5 text-xs data-[state=active]:bg-zinc-950 data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-3 whitespace-nowrap flex-shrink-0"
                >
                  <FileCode className="h-3 w-3" />
                  {name}
                  {isFileModified(name) && (
                    <Circle className="h-2 w-2 fill-yellow-500 text-yellow-500" />
                  )}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        {!readOnly && (
          <div className="flex items-center gap-2 px-2 shrink-0">
            {hasUnsavedChanges && (
              <span className="text-xs text-yellow-500 flex items-center gap-1">
                <Circle className="h-2 w-2 fill-yellow-500" />
                Unsaved changes
              </span>
            )}
          </div>
        )}
      </div>

      {/* Editor */}
      <div className="h-[400px]">
        <Editor
          language={getLanguage(activeFile)}
          theme="terraform-dark"
          value={editedFiles[activeFile] || ""}
          onChange={handleEditorChange}
          onMount={handleEditorMount}
          options={{
            readOnly: readOnly || !isEditing,
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: "on",
            scrollBeyondLastLine: false,
            wordWrap: "on",
            automaticLayout: true,
            tabSize: 2,
            padding: { top: 12, bottom: 12 },
            renderLineHighlight: "line",
            cursorBlinking: "smooth",
            smoothScrolling: true,
          }}
          loading={
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
            </div>
          }
        />
      </div>

      {/* Action Bar */}
      {!readOnly && (
        <div className="flex items-center justify-between border-t border-zinc-800 bg-zinc-900 px-3 py-2">
          <div className="flex items-center gap-2">
            <AnimatePresence>
              {saveError && (
                <motion.div
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -10 }}
                  className="flex items-center gap-1 text-xs text-red-400"
                >
                  <AlertCircle className="h-3 w-3" />
                  {saveError}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant={isEditing ? "default" : "ghost"}
              size="sm"
              onClick={() => {
                setIsEditing(!isEditing);
                if (!isEditing) {
                  editorRef.current?.focus();
                }
              }}
              className={`h-7 text-xs ${isEditing ? "bg-primary text-primary-foreground" : ""}`}
            >
              <Pencil className="mr-1 h-3 w-3" />
              {isEditing ? "Editing" : "Edit"}
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={handleDiscard}
              disabled={!hasUnsavedChanges || isSaving || !isEditing}
              className="h-7 text-xs"
            >
              <RotateCcw className="mr-1 h-3 w-3" />
              Discard
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={handleSave}
              disabled={!hasUnsavedChanges || isSaving || !isEditing}
              className="h-7 text-xs"
            >
              {isSaving ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : (
                <Save className="mr-1 h-3 w-3" />
              )}
              Save
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
