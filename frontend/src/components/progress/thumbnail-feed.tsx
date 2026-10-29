import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";

interface ThumbnailFeedProps {
  previews: string[];
}

export function ThumbnailFeed({ previews }: ThumbnailFeedProps) {
  if (previews.length === 0) return null;

  return (
    <ScrollArea className="w-full whitespace-nowrap rounded-md border bg-white">
      <div className="flex gap-2 p-3">
        {previews.map((src, i) => (
          <img
            key={`${src}-${i}`}
            src={src}
            alt=""
            className="h-20 w-28 shrink-0 rounded object-cover"
            loading="lazy"
          />
        ))}
      </div>
      <ScrollBar orientation="horizontal" />
    </ScrollArea>
  );
}
