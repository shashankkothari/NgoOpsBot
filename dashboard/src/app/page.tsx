import { redirect } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";

export default function RootPage() {
  if (isAuthenticated()) {
    redirect("/dashboard");
  } else {
    redirect("/login");
  }
}
