import DashboardShell from "@/components/DashboardShell";

export default function KnowledgeLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
