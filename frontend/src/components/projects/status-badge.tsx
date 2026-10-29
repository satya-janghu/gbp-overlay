import { Badge } from "@/components/ui/badge";

interface StatusBadgeProps {
  status: string;
}

const statusConfig: Record<string, { label: string; className: string }> = {
  processing: { label: "Processing", className: "bg-blue-100 text-blue-700" },
  crawling: { label: "Crawling", className: "bg-blue-100 text-blue-700" },
  classifying: { label: "Classifying", className: "bg-blue-100 text-blue-700" },
  review: { label: "Ready for Review", className: "bg-yellow-100 text-yellow-700" },
  crawled: { label: "Ready for Review", className: "bg-yellow-100 text-yellow-700" },
  previewing: { label: "Previewing", className: "bg-blue-100 text-blue-700" },
  generating: { label: "Generating", className: "bg-purple-100 text-purple-700" },
  complete: { label: "Complete", className: "bg-green-100 text-green-700" },
  failed: { label: "Failed", className: "bg-red-100 text-red-700" },
  setup: { label: "Setup", className: "bg-gray-100 text-gray-700" },
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status] ?? {
    label: status,
    className: "bg-gray-100 text-gray-700",
  };

  return (
    <Badge variant="secondary" className={config.className}>
      {config.label}
    </Badge>
  );
}
