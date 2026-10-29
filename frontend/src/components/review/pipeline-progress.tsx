import { Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { PipelineStatus } from "@/lib/api";

const stages = [
  { number: 1, label: "Crawling pages" },
  { number: 2, label: "Detecting locations" },
  { number: 3, label: "Classifying images" },
  { number: 4, label: "Generating previews" },
];

interface PipelineProgressProps {
  status: PipelineStatus;
}

export function PipelineProgress({ status }: PipelineProgressProps) {
  const progress = status.overall_progress ?? 0;
  const currentStage = status.stage_number ?? 1;

  return (
    <Card className="mx-auto max-w-lg">
      <CardHeader className="text-center">
        <CardTitle className="flex items-center justify-center gap-2">
          <Loader2 className="h-5 w-5 animate-spin" />
          Processing...
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <Progress value={progress} className="h-3" />
        <p className="text-center text-sm text-muted-foreground">
          {status.message ?? "Starting pipeline..."}
        </p>

        <div className="space-y-2">
          {stages.map((stage) => (
            <div
              key={stage.number}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm ${
                stage.number < currentStage
                  ? "text-muted-foreground line-through"
                  : stage.number === currentStage
                    ? "bg-primary/5 font-medium text-primary"
                    : "text-muted-foreground/50"
              }`}
            >
              <span className="w-5 text-center text-xs">{stage.number}</span>
              {stage.label}
              {stage.number === currentStage && (
                <Loader2 className="ml-auto h-3.5 w-3.5 animate-spin" />
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
