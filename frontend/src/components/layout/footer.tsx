import { Link } from "react-router-dom";
import { BookOpen } from "lucide-react";

export function Footer() {
  return (
    <footer className="border-t bg-white mt-auto">
      <div className="mx-auto flex h-12 max-w-5xl items-center justify-between px-4">
        <span className="text-sm text-muted-foreground">
          GBP Overlay &mdash; built by Satya Janghu
        </span>
        <Link
          to="/guide"
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <BookOpen className="h-4 w-4" />
          User Guide
        </Link>
      </div>
    </footer>
  );
}
