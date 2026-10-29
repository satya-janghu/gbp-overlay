import { Link, useLocation } from "react-router-dom";
import { ImageIcon, FolderOpen } from "lucide-react";
import { cn } from "@/lib/utils";

export function Navbar() {
  const location = useLocation();

  const links = [
    { to: "/", label: "New Project", icon: ImageIcon },
    { to: "/projects", label: "Projects", icon: FolderOpen },
  ];

  return (
    <nav className="border-b bg-white">
      <div className="mx-auto flex h-14 max-w-5xl items-center gap-6 px-4">
        <Link to="/" className="flex items-center gap-2 font-semibold text-lg">
          <ImageIcon className="h-5 w-5 text-primary" />
          GBP Overlay
        </Link>
        <div className="flex gap-1">
          {links.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                location.pathname === link.to
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <link.icon className="h-4 w-4" />
              {link.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
