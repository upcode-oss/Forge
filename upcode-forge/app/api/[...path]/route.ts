import { proxy } from "@/lib/proxy";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
