import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getPreviewImageUrl, type ProjectImage } from "@/lib/api";

interface ReviewCardProps {
  image: ProjectImage;
  projectId: number;
  keywords: string[];
  allLocations: string[];
  included: boolean;
  onToggleInclude: (id: number, included: boolean) => void;
  onKeywordChange: (id: number, keyword: string) => void;
  onLocationChange: (id: number, location: string) => void;
}

function confidenceColor(c: number | null): string {
  if (c === null) return "bg-gray-100 text-gray-600";
  if (c >= 0.7) return "bg-green-100 text-green-700";
  if (c >= 0.4) return "bg-yellow-100 text-yellow-700";
  return "bg-red-100 text-red-700";
}

export function ReviewCard({
  image,
  projectId,
  keywords,
  allLocations,
  included,
  onToggleInclude,
  onKeywordChange,
  onLocationChange,
}: ReviewCardProps) {
  const [localLocation, setLocalLocation] = useState(image.location ?? "");
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    setLocalLocation(image.location ?? "");
  }, [image.location]);

  return (
    <div
      className={`overflow-hidden rounded-lg border bg-white p-3 transition-opacity ${
        !included ? "opacity-50" : ""
      }`}
    >
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="flex shrink-0 flex-col items-center gap-2">
          <Checkbox
            checked={included}
            onCheckedChange={(v) => onToggleInclude(image.id, !!v)}
          />
          {imgError ? (
            <div className="flex h-20 w-28 items-center justify-center rounded bg-gray-100 text-xs text-muted-foreground">
              No preview
            </div>
          ) : (
            <img
              src={getPreviewImageUrl(projectId, image.id)}
              alt=""
              className="h-20 w-28 rounded object-cover"
              loading="lazy"
              onError={() => setImgError(true)}
            />
          )}
        </div>

        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <Badge className={confidenceColor(image.confidence)} variant="secondary">
              {image.confidence !== null
                ? `${Math.round(image.confidence * 100)}%`
                : "N/A"}
            </Badge>
            {image.source_page_url && (
              <span className="min-w-0 truncate text-xs text-muted-foreground">
                {image.source_page_url}
              </span>
            )}
          </div>

          <Select
            value={image.keyword ?? undefined}
            onValueChange={(v) => { if (v !== null) onKeywordChange(image.id, v); }}
          >
            <SelectTrigger className="h-8 text-sm">
              <SelectValue placeholder="Select keyword" />
            </SelectTrigger>
            <SelectContent>
              {keywords.map((kw) => (
                <SelectItem key={kw} value={kw}>
                  {kw}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Input
            value={localLocation}
            onChange={(e) => setLocalLocation(e.target.value)}
            onBlur={() => onLocationChange(image.id, localLocation)}
            placeholder="Location"
            className="h-8 text-sm"
            list={`locations-${image.id}`}
          />
          <datalist id={`locations-${image.id}`}>
            {allLocations.map((loc) => (
              <option key={loc} value={loc} />
            ))}
          </datalist>
        </div>
      </div>
    </div>
  );
}
