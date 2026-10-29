import { useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Eye, EyeOff, Copy, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { KeywordGroup } from "./keyword-group";
import {
  confirmReview,
  updateImageKeyword,
  updateImageLocation,
  getPreviewImageUrl,
  ApiError,
  type ProjectDetail,
  type ProjectImage,
} from "@/lib/api";

interface ReviewUIProps {
  data: ProjectDetail;
  onRefresh: () => void;
}

export function ReviewUI({ data, onRefresh }: ReviewUIProps) {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track which images are included (lazy initializer — only runs once)
  const [includedIds, setIncludedIds] = useState<Set<number>>(() => {
    const ids = new Set<number>();
    for (const group of data.keyword_groups) {
      for (const img of group.images) {
        ids.add(img.id);
      }
    }
    return ids;
  });

  // Track local overrides for optimistic updates
  const [overrides, setOverrides] = useState<
    Map<number, { keyword?: string; location?: string }>
  >(new Map());

  const toggleInclude = (id: number, included: boolean) => {
    setIncludedIds((prev) => {
      const next = new Set(prev);
      if (included) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  };

  // AbortControllers for in-flight requests — cancel stale ones
  const keywordAbortMap = useRef(new Map<number, AbortController>());
  const locationAbortMap = useRef(new Map<number, AbortController>());
  const keywordTimerMap = useRef(new Map<number, ReturnType<typeof setTimeout>>());
  const locationTimerMap = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  // Error-specific toast messages
  const toastApiError = (action: string, err: unknown) => {
    if (err instanceof ApiError) {
      if (err.status === 0) return; // Cancelled — no toast needed
      if (err.status === 400) toast.error(`Invalid ${action}`);
      else if (err.status === 404) toast.error(`${action}: image not found`);
      else if (err.status >= 500) toast.error(`Server error updating ${action}. Try again.`);
      else toast.error(`Failed to update ${action} (${err.status})`);
    } else {
      toast.error(`Failed to update ${action}`);
    }
  };

  const handleKeywordChange = useCallback((id: number, keyword: string) => {
    // Optimistic local update
    setOverrides((prev) => {
      const next = new Map(prev);
      const existing = next.get(id) ?? {};
      next.set(id, { ...existing, keyword });
      return next;
    });

    // Debounce 300ms + cancel previous in-flight request
    const existingTimer = keywordTimerMap.current.get(id);
    if (existingTimer) clearTimeout(existingTimer);

    const timer = setTimeout(() => {
      const prevController = keywordAbortMap.current.get(id);
      if (prevController) prevController.abort();

      const controller = new AbortController();
      keywordAbortMap.current.set(id, controller);

      updateImageKeyword(id, keyword, { signal: controller.signal }).catch((err) => {
        toastApiError("keyword", err);
        onRefresh();
      });
    }, 300);
    keywordTimerMap.current.set(id, timer);
  }, [onRefresh]);

  const handleLocationChange = useCallback((id: number, location: string) => {
    setOverrides((prev) => {
      const next = new Map(prev);
      const existing = next.get(id) ?? {};
      next.set(id, { ...existing, location });
      return next;
    });

    // Debounce 300ms + cancel previous in-flight request
    const existingTimer = locationTimerMap.current.get(id);
    if (existingTimer) clearTimeout(existingTimer);

    const timer = setTimeout(() => {
      const prevController = locationAbortMap.current.get(id);
      if (prevController) prevController.abort();

      const controller = new AbortController();
      locationAbortMap.current.set(id, controller);

      updateImageLocation(id, location, { signal: controller.signal }).catch((err) => {
        toastApiError("location", err);
        onRefresh();
      });
    }, 300);
    locationTimerMap.current.set(id, timer);
  }, [onRefresh]);

  const handleConfirm = async () => {
    setSubmitting(true);
    setError(null);

    const overridesList = Array.from(overrides.entries()).map(
      ([image_id, changes]) => ({ image_id, ...changes }),
    );

    try {
      const result = await confirmReview(data.project.id, {
        included_images: Array.from(includedIds),
        overrides: overridesList,
      });
      navigate(`/project/${result.id}/progress`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to confirm");
      setSubmitting(false);
    }
  };

  const includedCount = includedIds.size;

  return (
    <div className="space-y-6">
      {error && (
        <div className="flex items-center gap-2 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">
            Review Images
            {data.project.client_name && (
              <span className="ml-2 text-muted-foreground">
                — {data.project.client_name}
              </span>
            )}
          </h2>
          <p className="text-sm text-muted-foreground">
            {includedCount} images selected for overlay generation
          </p>
        </div>
        <Button
          onClick={handleConfirm}
          disabled={submitting || includedCount === 0}
          size="lg"
        >
          {submitting ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Generating...
            </>
          ) : (
            `Generate All (${includedCount} images)`
          )}
        </Button>
      </div>

      {/* Main keyword groups */}
      <div className="space-y-4">
        {data.keyword_groups.map((group) => (
          <KeywordGroup
            key={group.keyword}
            keyword={group.keyword}
            images={group.images}
            projectId={data.project.id}
            keywords={data.keywords}
            allLocations={data.all_locations}
            includedIds={includedIds}
            onToggleInclude={toggleInclude}
            onKeywordChange={handleKeywordChange}
            onLocationChange={handleLocationChange}
          />
        ))}
      </div>

      {/* Auto-skipped section */}
      {data.auto_skipped.length > 0 && (
        <CollapsibleSection
          title="Auto-deselected"
          icon={<EyeOff className="h-4 w-4" />}
          count={data.auto_skipped.length}
          images={data.auto_skipped}
          projectId={data.project.id}
        />
      )}

      {/* Duplicates section */}
      {data.duplicates.length > 0 && (
        <CollapsibleSection
          title="Duplicates"
          icon={<Copy className="h-4 w-4" />}
          count={data.duplicates.length}
          images={data.duplicates}
          projectId={data.project.id}
        />
      )}

      {/* Skipped section */}
      {data.skipped.length > 0 && (
        <CollapsibleSection
          title="Skipped"
          icon={<Eye className="h-4 w-4" />}
          count={data.skipped.length}
          images={data.skipped}
          projectId={data.project.id}
        />
      )}
    </div>
  );
}

function CollapsibleSection({
  title,
  icon,
  count,
  images,
  projectId,
}: {
  title: string;
  icon: React.ReactNode;
  count: number;
  images: ProjectImage[];
  projectId: number;
}) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-md border bg-white px-4 py-2.5 text-sm font-medium hover:bg-gray-50">
        {icon}
        <span className="flex-1 text-left">{title}</span>
        <Badge className="shrink-0" variant="secondary">{count}</Badge>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-2">
        <div className="flex flex-wrap gap-2 overflow-x-auto rounded-md border bg-gray-50 p-3">
          {images.map((img) => (
            <img
              key={img.id}
              src={getPreviewImageUrl(projectId, img.id)}
              alt=""
              className="h-16 w-24 rounded object-cover opacity-60"
              loading="lazy"
            />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
