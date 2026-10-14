import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";

interface PlaceholderPageProps {
  title: string;
  description: string;
}

export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return <><PageHeader title={title} description={description} /><EmptyState title={`${title} is coming next`} description="This workspace is reserved for a later implementation milestone. No operational data is shown yet." /></>;
}
