import { useQuery } from "@tanstack/react-query";
import { fetchProject } from "@/lib/api";

export function useProject(id: number) {
  return useQuery({
    queryKey: ["project", id],
    queryFn: () => fetchProject(id),
  });
}
