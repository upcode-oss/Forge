import { CircleAlert, FolderGit2, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
export function Loading() {
  return (
    <div className="state" role="status">
      <LoaderCircle className="spin" />
      Loading…
    </div>
  );
}
export function ErrorState({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="state error-state" role="alert">
      <CircleAlert />
      <strong>{message}</strong>
      {retry && (
        <Button variant="outline" onClick={retry}>
          Try again
        </Button>
      )}
    </div>
  );
}
export function Empty({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="state empty-state">
      <FolderGit2 />
      <strong>{title}</strong>
      <span>{description}</span>
    </div>
  );
}
