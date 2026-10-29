import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface StepIndicatorProps {
  currentStep: number;
}

const steps = [
  { number: 1, label: "Setup" },
  { number: 2, label: "Review" },
  { number: 3, label: "Download" },
];

export function StepIndicator({ currentStep }: StepIndicatorProps) {
  return (
    <div className="flex items-center justify-center gap-2 py-4">
      {steps.map((step, i) => (
        <div key={step.number} className="flex items-center gap-2">
          <div
            className={cn(
              "flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium",
              step.number < currentStep &&
                "bg-primary text-primary-foreground",
              step.number === currentStep &&
                "border-2 border-primary bg-white text-primary",
              step.number > currentStep &&
                "border border-muted-foreground/30 text-muted-foreground",
            )}
          >
            {step.number < currentStep ? (
              <Check className="h-3.5 w-3.5" />
            ) : (
              step.number
            )}
          </div>
          <span
            className={cn(
              "text-sm",
              step.number === currentStep
                ? "font-medium text-foreground"
                : "text-muted-foreground",
            )}
          >
            {step.label}
          </span>
          {i < steps.length - 1 && (
            <div
              className={cn(
                "mx-2 h-px w-12",
                step.number < currentStep ? "bg-primary" : "bg-border",
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}
