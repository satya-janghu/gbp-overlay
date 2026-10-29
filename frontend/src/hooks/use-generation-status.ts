import { useQuery } from "@tanstack/react-query";
import { fetchGenerationStatus, type GenerationStatus } from "@/lib/api";

export function useGenerationStatus(id: number, enabled: boolean) {
  return useQuery({
    queryKey: ["generation-status", id],
    queryFn: () => fetchGenerationStatus(id),
    refetchInterval: (query) => {
      const data = query.state.data as GenerationStatus | undefined;
      if (data?.status === "complete" || data?.status === "failed") {
        return false;
      }
      return enabled ? 3000 : false;
    },
    enabled,
  });
}
