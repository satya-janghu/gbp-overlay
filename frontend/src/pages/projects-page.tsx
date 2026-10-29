import { Link } from "react-router-dom";
import { Loader2, AlertCircle, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProjectsTable } from "@/components/projects/projects-table";
import { useProjects } from "@/hooks/use-projects";

export function ProjectsPage() {
  const { data, isLoading, error } = useProjects();

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
        {error instanceof Error ? error.message : "Failed to load projects"}
      </div>
    );
  }

  const isEmpty =
    data.active.length === 0 &&
    data.completed.length === 0 &&
    data.failed.length === 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Projects</h1>
        <Button render={<Link to="/" />}>
          <Plus className="mr-1.5 h-4 w-4" />
          New Project
        </Button>
      </div>

      {isEmpty ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">No projects yet.</p>
            <Button className="mt-4" render={<Link to="/" />}>
              Create Your First Project
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          {data.active.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Active Projects</CardTitle>
              </CardHeader>
              <CardContent>
                <ProjectsTable projects={data.active} />
              </CardContent>
            </Card>
          )}

          {data.completed.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Completed</CardTitle>
              </CardHeader>
              <CardContent>
                <ProjectsTable projects={data.completed} showDownload />
              </CardContent>
            </Card>
          )}

          {data.failed.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Failed</CardTitle>
              </CardHeader>
              <CardContent>
                <ProjectsTable projects={data.failed} />
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
