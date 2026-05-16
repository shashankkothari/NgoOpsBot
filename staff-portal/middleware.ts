export { default } from "next-auth/middleware";

export const config = {
  matcher: ["/chat/:path*", "/reminders/:path*", "/support/:path*", "/documents/:path*", "/settings/:path*"],
};
