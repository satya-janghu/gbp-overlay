import { useState } from "react";
import { ChevronDown, Globe, Upload, Sparkles, Zap, Download, Image, Type, MapPin, FileText } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

function Accordion({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between py-3 text-left text-sm font-medium hover:text-primary transition-colors"
      >
        {question}
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open && <p className="pb-3 text-sm text-muted-foreground leading-relaxed">{answer}</p>}
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h2 className="text-xl font-semibold mt-10 mb-4">{children}</h2>;
}

function StepCard({ number, title, description }: { number: number; title: string; description: string }) {
  return (
    <div className="flex gap-3">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-white text-sm font-semibold">
        {number}
      </div>
      <div>
        <p className="font-medium text-sm">{title}</p>
        <p className="text-sm text-muted-foreground mt-0.5">{description}</p>
      </div>
    </div>
  );
}

const faqs = [
  {
    q: "What image formats are supported?",
    a: "JPEG, PNG, and WebP. All output images are converted to JPEG for GBP compatibility.",
  },
  {
    q: "Can I upload images instead of crawling a website?",
    a: "Yes. Leave the Website URL field blank, then drag-drop or browse to upload your images. The AI will still classify them against your keywords.",
  },
  {
    q: "Can I combine website fetch with manual uploads?",
    a: "Yes. Provide a website URL and also upload images. Both sets will be processed together in the same project.",
  },
  {
    q: "How long do downloads stay available?",
    a: "ZIP downloads are available for 24 hours after generation. After that, the files are automatically cleaned up. You can always re-generate from the project.",
  },
  {
    q: 'What does "Fetch From Anywhere" do?',
    a: "By default, the crawler focuses on location-related pages (e.g., /locations/, /service-area/). Enabling this option tells it to fetch images from every page on the site.",
  },
  {
    q: 'What does "JS-rendered site" do?',
    a: "Some websites load content dynamically with JavaScript. Enable this if the site uses a framework like React or Angular and images aren't found with the default crawler. It uses a headless browser (slower but more thorough).",
  },
  {
    q: "How does the AI decide which keyword matches an image?",
    a: "The app sends each image to Google's Gemini 2.5 Flash vision model along with your keyword list. Gemini analyzes the image content and returns the best-matching keyword with a confidence score (0-1). Matches with confidence 0.4 or higher are pre-selected; weaker matches are auto-deselected so you can review and restore them.",
  },
  {
    q: "Can I override the AI's keyword suggestion?",
    a: "Absolutely. On the Review page, every image has a keyword dropdown. You can change the assigned keyword, edit the location, or exclude images entirely before generating overlays.",
  },
  {
    q: "What's the minimum image size?",
    a: "Images must be at least 720px wide. Smaller images are automatically filtered out during crawling since they won't look good on Google Business Profile.",
  },
  {
    q: "How are duplicate images handled?",
    a: "The app computes a perceptual hash for every image and compares them. Images that are 90%+ visually similar are marked as duplicates and skipped to avoid wasting processing on near-identical images.",
  },
  {
    q: "Where does the overlay get placed on images?",
    a: "A Python algorithm analyzes each image to find the best overlay position. It scores regions based on luminance uniformity and visual saliency (avoiding important content), then places the text bar in the optimal spot. This is not AI \u2014 it's a deterministic image analysis algorithm.",
  },
  {
    q: "Can I use this for multiple locations at once?",
    a: "Yes. Enter multiple locations (one per line) in the setup form. The app will distribute images across locations using round-robin assignment when locations can't be inferred from the page URL.",
  },
  {
    q: "What if I don't provide locations?",
    a: "The app will attempt to infer locations from URL patterns and page content using AI. If no location can be determined, images will have the keyword overlay only (no location line).",
  },
];

export function GuidePage() {
  return (
    <div className="space-y-2">
      {/* Hero */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">User Guide</h1>
        <p className="text-muted-foreground mt-1">
          Learn how to use the GBP Image Overlay tool to prepare optimized images for Google Business Profile.
        </p>
      </div>

      {/* Two Workflows */}
      <SectionHeading>Two Ways to Get Started</SectionHeading>
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardContent className="pt-5 space-y-3">
            <div className="flex items-center gap-2">
              <Globe className="h-5 w-5 text-primary" />
              <h3 className="font-semibold">Auto-Fetch from Website</h3>
            </div>
            <ol className="space-y-2 text-sm text-muted-foreground list-decimal list-inside">
              <li>Enter a website URL along with your keywords and locations</li>
              <li>The app crawls the site, finds location pages, and extracts images</li>
              <li>AI matches images to your keywords &mdash; you review and confirm</li>
              <li>Generate text overlays and download the ZIP</li>
            </ol>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5 space-y-3">
            <div className="flex items-center gap-2">
              <Upload className="h-5 w-5 text-primary" />
              <h3 className="font-semibold">Manual Upload</h3>
            </div>
            <ol className="space-y-2 text-sm text-muted-foreground list-decimal list-inside">
              <li>Enter your keywords and locations (no website URL needed)</li>
              <li>Drag-drop or browse to upload your images</li>
              <li>AI matches uploaded images to keywords &mdash; you review and confirm</li>
              <li>Generate text overlays and download the ZIP</li>
            </ol>
          </CardContent>
        </Card>
      </div>

      {/* Step-by-Step */}
      <SectionHeading>Step-by-Step Walkthrough</SectionHeading>
      <Card>
        <CardContent className="pt-5 space-y-5">
          <StepCard
            number={1}
            title="Setup"
            description="Enter your client name, keywords (one per line), and locations. Choose a font for the overlay text. Either provide a website URL for auto-fetching or upload images directly."
          />
          <StepCard
            number={2}
            title="Crawl / Process"
            description="If you provided a URL, the app fetches the sitemap, crawls pages, and downloads qualifying images (720px+ wide). Duplicate images are automatically removed. If you uploaded images, this step is skipped."
          />
          <StepCard
            number={3}
            title="Review"
            description="AI analyzes each image and suggests the best keyword match. You can confirm, change, or exclude any image. Locations are auto-detected from page URLs and content, or assigned from your list."
          />
          <StepCard
            number={4}
            title="Generate"
            description="Python renders text overlays on each image — keyword on top, location below. The overlay position, color, and contrast are automatically optimized for each image."
          />
          <StepCard
            number={5}
            title="Download"
            description="All overlaid images are packaged into a ZIP file with a CSV manifest listing every image's filename, keyword, location, and source. Downloads are available for 24 hours."
          />
        </CardContent>
      </Card>

      {/* Features */}
      <SectionHeading>Features</SectionHeading>
      <div className="grid gap-3 sm:grid-cols-2">
        {[
          { icon: Globe, label: "Smart Crawling", desc: "Sitemap parsing, location page detection, per-domain rate limiting, and image deduplication" },
          { icon: Upload, label: "Manual Image Upload", desc: "Drag-drop or browse to upload images in bulk — JPEG, PNG, or WebP" },
          { icon: Sparkles, label: "AI Keyword Matching", desc: "Gemini 2.5 Flash vision model classifies images against your keyword list with confidence scoring" },
          { icon: Zap, label: "Intelligent Overlay Placement", desc: "Algorithm analyzes luminance and saliency to place text where it won't obscure important content" },
          { icon: Type, label: "9 Google Fonts", desc: "Montserrat, Poppins, Oswald, Roboto, Playfair Display, Lato, Bebas Neue, Raleway, and Nunito" },
          { icon: Download, label: "Bulk Processing & ZIP Export", desc: "Process hundreds of images at once with a CSV manifest for easy tracking" },
        ].map((f) => (
          <div key={f.label} className="flex gap-3 rounded-lg border p-3">
            <f.icon className="h-5 w-5 shrink-0 text-primary mt-0.5" />
            <div>
              <p className="text-sm font-medium">{f.label}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{f.desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Tips */}
      <SectionHeading>Tips & Best Practices</SectionHeading>
      <Card>
        <CardContent className="pt-5 space-y-4">
          <div className="flex gap-3">
            <FileText className="h-5 w-5 shrink-0 text-primary mt-0.5" />
            <div>
              <p className="text-sm font-medium">Keywords</p>
              <p className="text-sm text-muted-foreground">Be specific rather than generic. "Roof Repair" works better than "Roofing". Use the same phrasing you'd want displayed on the image overlay.</p>
            </div>
          </div>
          <div className="flex gap-3">
            <MapPin className="h-5 w-5 shrink-0 text-primary mt-0.5" />
            <div>
              <p className="text-sm font-medium">Locations</p>
              <p className="text-sm text-muted-foreground">Use "City, State" format (e.g., "Springfield, IL"). Always provide locations when uploading images manually, since there's no URL to infer them from.</p>
            </div>
          </div>
          <div className="flex gap-3">
            <Type className="h-5 w-5 shrink-0 text-primary mt-0.5" />
            <div>
              <p className="text-sm font-medium">Font Selection</p>
              <p className="text-sm text-muted-foreground">Bold sans-serif fonts (Montserrat, Poppins, Oswald) are most readable at small sizes. Playfair Display works well for premium/luxury brands.</p>
            </div>
          </div>
          <div className="flex gap-3">
            <Image className="h-5 w-5 shrink-0 text-primary mt-0.5" />
            <div>
              <p className="text-sm font-medium">Images Per Page</p>
              <p className="text-sm text-muted-foreground">Default is 1 image per page. Increase if you need more variety, but higher values mean more images to review and longer processing time.</p>
            </div>
          </div>
          <div className="flex gap-3">
            <Globe className="h-5 w-5 shrink-0 text-primary mt-0.5" />
            <div>
              <p className="text-sm font-medium">Auto-Fetch vs. Upload</p>
              <p className="text-sm text-muted-foreground">Use auto-fetch when the client's website has good, high-resolution images on location pages. Use upload when you have curated images ready or the website doesn't have suitable images.</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* FAQ */}
      <SectionHeading>Frequently Asked Questions</SectionHeading>
      <Card>
        <CardContent className="pt-2 pb-0">
          {faqs.map((faq) => (
            <Accordion key={faq.q} question={faq.q} answer={faq.a} />
          ))}
        </CardContent>
      </Card>

      <div className="h-6" />
    </div>
  );
}
