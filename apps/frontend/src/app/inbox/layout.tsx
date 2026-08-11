import DashboardShell from "@/components/DashboardShell";

export default function InboxLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
