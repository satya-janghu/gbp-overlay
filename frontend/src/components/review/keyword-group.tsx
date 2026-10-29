import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ReviewCard } from "./review-card";
import type { ProjectImage } from "@/lib/api";

interface KeywordGroupProps {
  keyword: string;
  images: ProjectImage[];
  projectId: number;
  keywords: string[];
  allLocations: string[];
  includedIds: Set<number>;
  onToggleInclude: (id: number, included: boolean) => void;
  onKeywordChange: (id: number, keyword: string) => void;
  onLocationChange: (id: number, location: string) => void;
}

export function KeywordGroup({
  keyword,
  images,
  projectId,
  keywords,
  allLocations,
  includedIds,
  onToggleInclude,
  onKeywordChange,
  onLocationChange,
}: KeywordGroupProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 rounded-md bg-secondary px-3 py-2 text-left text-sm font-medium hover:bg-secondary/80"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        <span className="flex-1">{keyword}</span>
        <Badge variant="outline">{images.length}</Badge>
      </button>

      {expanded && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {images.map((img) => (
            <ReviewCard
              key={img.id}
              image={img}
              projectId={projectId}
              keywords={keywords}
              allLocations={allLocations}
              included={includedIds.has(img.id)}
              onToggleInclude={onToggleInclude}
              onKeywordChange={onKeywordChange}
              onLocationChange={onLocationChange}
            />
          ))}
        </div>
      )}
    </div>
  );
}
