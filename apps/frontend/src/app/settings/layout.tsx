import DashboardShell from "@/components/DashboardShell";

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DashboardShell>{children}</DashboardShell>;
}
