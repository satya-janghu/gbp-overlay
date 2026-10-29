import { getFonts } from "@/lib/api";

interface FontPickerProps {
  value: string;
  onChange: (font: string) => void;
}

const fonts = getFonts();
const fontNames = Object.keys(fonts);

export function FontPicker({ value, onChange }: FontPickerProps) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">Font</label>
      <div className="grid grid-cols-3 gap-2">
        {fontNames.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => onChange(name)}
            className={`rounded-md border p-3 text-left transition-colors ${
              value === name
                ? "border-primary bg-primary/5 ring-1 ring-primary"
                : "border-border hover:border-primary/50"
            }`}
          >
            <span
              className="block text-lg font-bold leading-tight"
              style={{ fontFamily: `'${name}', sans-serif` }}
            >
              Roof Repair
            </span>
            <span
              className="block text-sm leading-tight text-muted-foreground"
              style={{ fontFamily: `'${name}', sans-serif` }}
            >
              Springfield, IL
            </span>
            <span className="mt-1 block text-xs text-muted-foreground">
              {name}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
