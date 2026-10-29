import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FontPicker } from "./font-picker";
import { FileDropzone } from "./file-dropzone";
import { toast } from "sonner";
import { createProject } from "@/lib/api";

const schema = z.object({
  client_name: z.string().optional(),
  website_url: z.string().optional(),
  keywords: z.string().min(1, "At least one keyword is required"),
  locations: z.string().optional(),
  font: z.string(),
  images_per_page: z.coerce.number().min(1).max(50),
  fetch_anywhere: z.boolean(),
  js_rendered: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

export function SetupForm() {
  const navigate = useNavigate();
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      font: "Montserrat",
      images_per_page: 1,
      fetch_anywhere: false,
      js_rendered: false,
    },
  });

  const font = watch("font");
  const fetchAnywhere = watch("fetch_anywhere");
  const jsRendered = watch("js_rendered");

  const onSubmit = async (data: FormValues) => {
    if (!data.website_url?.trim() && files.length === 0) {
      setError("Please provide a website URL or upload images.");
      return;
    }

    setSubmitting(true);
    setError(null);

    const formData = new FormData();
    formData.append("client_name", data.client_name ?? "");
    formData.append("website_url", data.website_url ?? "");
    formData.append("keywords", data.keywords);
    formData.append("locations", data.locations ?? "");
    formData.append("font", data.font);
    formData.append("images_per_page", String(data.images_per_page));
    formData.append("fetch_anywhere", String(data.fetch_anywhere));
    formData.append("js_rendered", String(data.js_rendered));

    for (const file of files) {
      formData.append("files", file);
    }

    try {
      const result = await createProject(formData);
      toast.success("Project created successfully");
      navigate(`/project/${result.id}/review`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create project";
      setError(message);
      toast.error(message);
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      {error && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Project Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="client_name">Client Name</Label>
              <Input
                id="client_name"
                placeholder="e.g., Smith Roofing"
                {...register("client_name")}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="website_url">Website URL</Label>
              <Input
                id="website_url"
                type="url"
                placeholder="https://example.com"
                {...register("website_url")}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="keywords">
              Keywords <span className="text-destructive">*</span>
            </Label>
            <Textarea
              id="keywords"
              placeholder="One keyword per line, e.g.:&#10;Roof Repair&#10;Gutter Installation&#10;Storm Damage"
              rows={4}
              {...register("keywords")}
            />
            {errors.keywords && (
              <p className="text-xs text-destructive">{errors.keywords.message}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="locations">Locations</Label>
            <Textarea
              id="locations"
              placeholder="One location per line (optional), e.g.:&#10;Chicago, IL&#10;Springfield, IL"
              rows={3}
              {...register("locations")}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="images_per_page">Images per page</Label>
              <Input
                id="images_per_page"
                type="number"
                min={1}
                max={50}
                {...register("images_per_page")}
              />
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <Checkbox
                id="fetch_anywhere"
                checked={fetchAnywhere}
                onCheckedChange={(v) => setValue("fetch_anywhere", !!v)}
              />
              <Label htmlFor="fetch_anywhere" className="text-sm font-normal">
                Fetch from any page
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="js_rendered"
                checked={jsRendered}
                onCheckedChange={(v) => setValue("js_rendered", !!v)}
              />
              <Label htmlFor="js_rendered" className="text-sm font-normal">
                JS-rendered site
              </Label>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <FileDropzone files={files} onChange={setFiles} />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <FontPicker value={font} onChange={(v) => setValue("font", v)} />
        </CardContent>
      </Card>

      <Button type="submit" size="lg" className="w-full" disabled={submitting}>
        {submitting ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Creating Project...
          </>
        ) : (
          "Start Project"
        )}
      </Button>
    </form>
  );
}
