import { StepIndicator } from "@/components/layout/step-indicator";
import { SetupForm } from "@/components/setup/setup-form";

export function SetupPage() {
  return (
    <>
      <StepIndicator currentStep={1} />
      <SetupForm />
    </>
  );
}
