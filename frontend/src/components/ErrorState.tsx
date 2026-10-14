interface ErrorStateProps {
  message?: string;
}

export function ErrorState({ message = "We could not load this workspace." }: ErrorStateProps) {
  return <div className="state-card error-state" role="alert"><strong>Something went wrong</strong><p>{message}</p></div>;
}
