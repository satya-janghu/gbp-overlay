import { useParams, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { Loader2, AlertCircle } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { StepIndicator } from "@/components/layout/step-indicator";
import { PipelineProgress } from "@/components/review/pipeline-progress";
import { ReviewUI } from "@/components/review/review-ui";
import { useProject } from "@/hooks/use-project";
import { usePipelineStatus } from "@/hooks/use-pipeline-status";

const PROCESSING_STATUSES = new Set(["processing", "crawling", "classifying"]);
const REVIEW_STATUSES = new Set(["review", "crawled", "previewing"]);

export function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useProject(projectId);

  const projectStatus = data?.project.status ?? "";
  const isProcessing = PROCESSING_STATUSES.has(projectStatus);

  const { data: pipelineStatus } = usePipelineStatus(projectId, isProcessing);

  // When pipeline completes, refetch project data
  useEffect(() => {
    if (pipelineStatus?.status === "complete") {
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    }
  }, [pipelineStatus?.status, projectId, queryClient]);

  // Redirect based on status
  useEffect(() => {
    if (!data) return;
    const s = data.project.status;
    if (s === "generating") {
      navigate(`/project/${projectId}/progress`, { replace: true });
    } else if (s === "complete") {
      navigate("/projects", { replace: true });
    }
  }, [data, projectId, navigate]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center gap-2 py-20 text-destructive">
        <AlertCircle className="h-5 w-5" />
        {error instanceof Error ? error.message : "Failed to load project"}
      </div>
    );
  }

  return (
    <>
      <StepIndicator currentStep={2} />

      {isProcessing && pipelineStatus ? (
        <PipelineProgress status={pipelineStatus} />
      ) : isProcessing ? (
        <PipelineProgress
          status={{ status: "pending", message: "Starting pipeline..." }}
        />
      ) : REVIEW_STATUSES.has(projectStatus) || projectStatus === "failed" ? (
        <ReviewUI data={data} onRefresh={() => refetch()} />
      ) : null}
    </>
  );
}
