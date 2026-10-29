import { NextResponse } from "next/server";

// 鉴权：网页用 Basic Auth（用户名任意，密码 SITE_PASSWORD）；
// 接口另可用 Authorization: Bearer <SITE_API_TOKEN> 或 X-API-Key: <SITE_API_TOKEN>
// 两者都没配置时拒绝所有请求，避免漏配环境变量后整站裸奔。

const WRITE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// Basic 凭据按 UTF-8 解码（浏览器这样编码；atob 只给出逐字节的 latin1 串）
function basicPassword(auth) {
  try {
    const bin = atob(auth.slice(6));
    const decoded = new TextDecoder("utf-8", { fatal: true }).decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
    const i = decoded.indexOf(":");
    return i >= 0 ? decoded.slice(i + 1) : null;
  } catch {
    return null;
  }
}

// 浏览器会给跨站请求自动带 Basic 凭据：写操作必须来自同源（或不是浏览器发的，没有 Origin / Sec-Fetch-Site）
function crossSite(req) {
  const site = req.headers.get("sec-fetch-site");
  if (site && !["same-origin", "none"].includes(site)) return true;
  const origin = req.headers.get("origin");
  if (!origin) return false;
  if (origin === "null") return true;
  const host = req.headers.get("x-forwarded-host") || req.headers.get("host");
  try {
    return new URL(origin).host !== host;
  } catch {
    return true;
  }
}

const unauthorized = (req) =>
  req.nextUrl.pathname.startsWith("/api/")
    ? NextResponse.json({ error: { code: "unauthorized", message: "缺少或错误的 API Token，请在请求头加 Authorization: Bearer <token>" } }, { status: 401 })
    : new NextResponse("需要登录", { status: 401, headers: { "WWW-Authenticate": 'Basic realm="video-review", charset="UTF-8"' } });

export function middleware(req) {
  const pw = process.env.SITE_PASSWORD;
  const token = process.env.SITE_API_TOKEN;
  const auth = req.headers.get("authorization") || "";
  if (token && (auth === `Bearer ${token}` || req.headers.get("x-api-key") === token)) return NextResponse.next();
  if (pw && auth.startsWith("Basic ") && basicPassword(auth) === pw) {
    if (WRITE.has(req.method) && crossSite(req)) {
      return NextResponse.json({ error: { code: "forbidden", message: "拒绝跨站请求" } }, { status: 403 });
    }
    return NextResponse.next();
  }
  return unauthorized(req);
}

export const config = { matcher: "/((?!_next/static|favicon.ico).*)" };
