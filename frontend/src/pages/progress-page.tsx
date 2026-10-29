import { useParams } from "react-router-dom";
import { Loader2, AlertCircle } from "lucide-react";
import { StepIndicator } from "@/components/layout/step-indicator";
import { GenerationProgress } from "@/components/progress/generation-progress";
import { useGenerationStatus } from "@/hooks/use-generation-status";

export function ProgressPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = Number(id);

  const { data: status, isLoading, error } = useGenerationStatus(projectId, true);

  if (isLoading || !status) {
    return (
      <>
        <StepIndicator currentStep={3} />
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </>
    );
  }

  if (error) {
    return (
      <>
        <StepIndicator currentStep={3} />
        <div className="flex items-center justify-center gap-2 py-20 text-destructive">
          <AlertCircle className="h-5 w-5" />
          {error instanceof Error ? error.message : "Failed to load status"}
        </div>
      </>
    );
  }

  return (
    <>
      <StepIndicator currentStep={3} />
      <GenerationProgress projectId={projectId} status={status} />
    </>
  );
}
