import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DownloadButton } from "@/components/ui/download-button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusBadge } from "./status-badge";
import { type ProjectSummary } from "@/lib/api";

interface ProjectsTableProps {
  projects: ProjectSummary[];
  showDownload?: boolean;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatSize(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ProjectsTable({ projects, showDownload }: ProjectsTableProps) {
  if (projects.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-muted-foreground">
        No projects
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Client</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Created</TableHead>
          {showDownload && <TableHead>Images</TableHead>}
          {showDownload && <TableHead>Size</TableHead>}
          <TableHead className="text-right">Action</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {projects.map((p) => (
          <TableRow key={p.id}>
            <TableCell className="font-medium">
              {p.client_name ?? `Project #${p.id}`}
            </TableCell>
            <TableCell>
              <StatusBadge status={p.status} />
            </TableCell>
            <TableCell className="text-sm text-muted-foreground">
              {formatDate(p.created_at)}
            </TableCell>
            {showDownload && (
              <TableCell className="text-sm">
                {p.image_count ?? "—"}
              </TableCell>
            )}
            {showDownload && (
              <TableCell className="text-sm">
                {formatSize(p.zip_size)}
              </TableCell>
            )}
            <TableCell className="text-right">
              {showDownload && p.has_download ? (
                <DownloadButton
                  projectId={p.id}
                  variant="outline"
                  size="sm"
                  label="Download"
                />
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  render={<Link to={p.resume_url} />}
                >
                  <ArrowRight className="mr-1.5 h-3.5 w-3.5" />
                  Continue
                </Button>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
