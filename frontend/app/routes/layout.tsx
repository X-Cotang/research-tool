import { AppShell } from "~/components/AppShell";
import { RequireAuth } from "~/components/RequireAuth";

export default function LayoutRoute() {
  return (
    <RequireAuth>
      <AppShell />
    </RequireAuth>
  );
}
