interface EmptyStateProps {
  title: string;
  description: string;
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <section className="state-card" aria-live="polite">
      <span className="state-mark" aria-hidden="true">—</span>
      <h2>{title}</h2>
      <p>{description}</p>
    </section>
  );
}
