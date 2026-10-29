import { useQuery } from "@tanstack/react-query";
import { fetchPipelineStatus, type PipelineStatus } from "@/lib/api";

export function usePipelineStatus(id: number, enabled: boolean) {
  return useQuery({
    queryKey: ["pipeline-status", id],
    queryFn: () => fetchPipelineStatus(id),
    refetchInterval: (query) => {
      const data = query.state.data as PipelineStatus | undefined;
      if (data?.status === "complete" || data?.status === "failed") {
        return false;
      }
      return enabled ? 3000 : false;
    },
    enabled,
  });
}
