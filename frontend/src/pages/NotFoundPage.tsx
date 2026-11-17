import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="narrow">
      <h1>Page not found</h1>
      <p>
        <Link to="/">Back to the start</Link>
      </p>
    </section>
  );
}
