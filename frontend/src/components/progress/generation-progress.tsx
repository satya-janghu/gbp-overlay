import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Loader2, CheckCircle, AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { DownloadButton } from "@/components/ui/download-button";
import { ThumbnailFeed } from "./thumbnail-feed";
import { type GenerationStatus } from "@/lib/api";

interface GenerationProgressProps {
  projectId: number;
  status: GenerationStatus;
}

export function GenerationProgress({ projectId, status }: GenerationProgressProps) {
  const [previews, setPreviews] = useState<string[]>([]);

  const isComplete = status.status === "complete";
  const isFailed = status.status === "failed";
  const current = status.current ?? 0;
  const total = status.total ?? 1;
  const percent = total > 0 ? Math.round((current / total) * 100) : 0;
  const isEmptyComplete = isComplete && current === 0;

  useEffect(() => {
    if (status.latest_preview) {
      setPreviews((prev) =>
        prev.includes(status.latest_preview!)
          ? prev
          : [...prev, status.latest_preview!],
      );
    }
  }, [status.latest_preview]);

  return (
    <div className="mx-auto max-w-lg space-y-4">
      <Card>
        <CardHeader className="text-center">
          <CardTitle className="flex items-center justify-center gap-2">
            {isEmptyComplete ? (
              <>
                <AlertCircle className="h-5 w-5 text-amber-500" />
                No Images Generated
              </>
            ) : isComplete ? (
              <>
                <CheckCircle className="h-5 w-5 text-green-600" />
                Complete!
              </>
            ) : isFailed ? (
              <>
                <AlertCircle className="h-5 w-5 text-destructive" />
                Failed
              </>
            ) : (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                Generating Overlays...
              </>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Progress value={isComplete ? 100 : percent} className="h-3" />
          <p className="text-center text-sm text-muted-foreground">
            {isEmptyComplete
              ? "No images were available for overlay generation. Check that images have keywords and locations assigned."
              : isComplete
                ? `${current} images processed`
                : isFailed
                  ? (status.error ?? "Generation failed")
                  : `${current} / ${total} images`}
          </p>

          {isComplete && current > 0 && (
            <div className="flex justify-center gap-3 pt-2">
              <DownloadButton projectId={projectId} size="lg" />
              <Button variant="outline" render={<Link to="/projects" />}>
                View Projects
              </Button>
            </div>
          )}

          {isEmptyComplete && (
            <div className="flex justify-center gap-3 pt-2">
              <Button
                variant="outline"
                render={<Link to={`/project/${projectId}/review`} />}
              >
                Back to Review
              </Button>
            </div>
          )}

          {isFailed && (
            <div className="flex justify-center pt-2">
              <Button
                variant="outline"
                render={<Link to={`/project/${projectId}/review`} />}
              >
                Back to Review
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <ThumbnailFeed previews={previews} />
    </div>
  );
}
