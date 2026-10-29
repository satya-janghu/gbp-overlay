import { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { downloadZip } from "@/lib/api";

interface DownloadButtonProps {
  projectId: number;
  variant?: "default" | "outline" | "ghost";
  size?: "default" | "sm" | "lg" | "icon";
  label?: string;
}

export function DownloadButton({
  projectId,
  variant = "default",
  size = "default",
  label = "Download ZIP",
}: DownloadButtonProps) {
  const [isDownloading, setIsDownloading] = useState(false);

  async function handleClick() {
    setIsDownloading(true);
    try {
      await downloadZip(projectId);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Download failed";
      toast.error(message);
    } finally {
      setIsDownloading(false);
    }
  }

  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleClick}
      disabled={isDownloading}
    >
      {isDownloading ? (
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      ) : (
        <Download className="mr-2 h-4 w-4" />
      )}
      {label}
    </Button>
  );
}
