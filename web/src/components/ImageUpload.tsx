"use client";

import { useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload,
  Image as ImageIcon,
  X,
  FileImage,
  Loader2,
  Wand2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ImageUploadProps {
  onGenerate: (imageData: string, prompt: string) => Promise<void>;
  isLoading?: boolean;
}

export function ImageUpload({ onGenerate, isLoading = false }: ImageUploadProps) {
  const [dragActive, setDragActive] = useState(false);
  const [image, setImage] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [prompt, setPrompt] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const processFile = useCallback((file: File) => {
    if (!file.type.startsWith("image/")) {
      alert("Please upload an image file (PNG, JPG, etc.)");
      return;
    }

    if (file.size > 20 * 1024 * 1024) {
      alert("File size must be less than 20MB");
      return;
    }

    setFileName(file.name);

    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result as string;
      setImage(result);
    };
    reader.readAsDataURL(file);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);

      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        processFile(e.dataTransfer.files[0]);
      }
    },
    [processFile]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      e.preventDefault();
      if (e.target.files && e.target.files[0]) {
        processFile(e.target.files[0]);
      }
    },
    [processFile]
  );

  const handleRemove = () => {
    setImage(null);
    setFileName("");
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  };

  const handleGenerate = async () => {
    if (!image) return;
    await onGenerate(image, prompt);
  };

  return (
    <div className="space-y-4">
      {/* Upload Area */}
      <AnimatePresence mode="wait">
        {!image ? (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className={`relative rounded-lg border-2 border-dashed p-8 transition-colors ${
              dragActive
                ? "border-primary bg-primary/5"
                : "border-zinc-700 hover:border-zinc-500"
            }`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              onChange={handleChange}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />

            <div className="flex flex-col items-center justify-center text-center">
              <div className="rounded-full bg-zinc-800 p-4 mb-4">
                <Upload className="h-8 w-8 text-zinc-400" />
              </div>
              <h3 className="text-lg font-medium mb-2">
                Upload Architecture Diagram
              </h3>
              <p className="text-sm text-muted-foreground mb-4">
                Drag and drop your diagram here, or click to browse
              </p>
              <p className="text-xs text-muted-foreground">
                Supports PNG, JPG, WEBP (max 20MB)
              </p>
            </div>
          </motion.div>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="relative rounded-lg border border-zinc-700 overflow-hidden"
          >
            {/* Image Preview */}
            <div className="relative bg-zinc-900 p-4">
              <button
                onClick={handleRemove}
                className="absolute top-2 right-2 rounded-full bg-zinc-800 p-1.5 hover:bg-zinc-700 transition-colors z-10"
              >
                <X className="h-4 w-4" />
              </button>

              <div className="flex items-center gap-3 mb-3">
                <FileImage className="h-5 w-5 text-primary" />
                <span className="text-sm font-medium truncate">{fileName}</span>
              </div>

              <div className="relative rounded-md overflow-hidden bg-zinc-950 flex items-center justify-center min-h-[200px] max-h-[400px]">
                <img
                  src={image}
                  alt="Architecture diagram"
                  className="max-w-full max-h-[400px] object-contain"
                />
              </div>
            </div>

            {/* Context Input */}
            <div className="p-4 border-t border-zinc-700">
              <label className="block text-sm font-medium mb-2">
                Additional Context (optional)
              </label>
              <Textarea
                value={prompt}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setPrompt(e.target.value)}
                placeholder="E.g., 'Use t3.medium instances', 'Add CloudWatch monitoring', 'Make it production-ready with multi-AZ'..."
                className="min-h-[80px] bg-zinc-900 border-zinc-700 resize-none"
              />
            </div>

            {/* Generate Button */}
            <div className="p-4 border-t border-zinc-700 bg-zinc-900/50">
              <Button
                onClick={handleGenerate}
                disabled={isLoading}
                className="w-full"
                size="lg"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    Analyzing Diagram...
                  </>
                ) : (
                  <>
                    <Wand2 className="mr-2 h-5 w-5" />
                    Generate Terraform from Diagram
                  </>
                )}
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Tips */}
      {!image && (
        <div className="rounded-lg bg-zinc-900/50 p-4">
          <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
            <ImageIcon className="h-4 w-4 text-primary" />
            Tips for best results
          </h4>
          <ul className="text-xs text-muted-foreground space-y-1">
            <li>• Use clear, high-resolution diagrams</li>
            <li>• AWS/GCP/Azure architecture diagrams work best</li>
            <li>• Include resource names and connections</li>
            <li>• Hand-drawn diagrams are also supported</li>
          </ul>
        </div>
      )}
    </div>
  );
}
