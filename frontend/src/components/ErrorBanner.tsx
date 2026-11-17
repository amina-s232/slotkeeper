import { ApiError } from "../api/client";

/** Shows an error from the API in plain words. Renders nothing when there is no error. */
export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <p role="alert" className="banner banner-error">
      {message}
    </p>
  );
}

/** The message for one form field, from a 400 response's per-field errors. */
export function fieldError(error: unknown, field: string): string | undefined {
  return error instanceof ApiError ? error.fields[field]?.[0] : undefined;
}
