import { NextResponse } from "next/server";

// 鉴权：网页用 Basic Auth（用户名任意，密码 SITE_PASSWORD）；
// 接口另可用 Authorization: Bearer <SITE_API_TOKEN> 或 X-API-Key: <SITE_API_TOKEN>
export function middleware(req) {
  const pw = process.env.SITE_PASSWORD;
  const token = process.env.SITE_API_TOKEN;
  if (!pw && !token) return NextResponse.next();
  const auth = req.headers.get("authorization") || "";
  if (token && (auth === `Bearer ${token}` || req.headers.get("x-api-key") === token)) return NextResponse.next();
  if (pw && auth.startsWith("Basic ")) {
    try {
      const decoded = atob(auth.slice(6));
      if (decoded.slice(decoded.indexOf(":") + 1) === pw) return NextResponse.next();
    } catch {}
  }
  if (req.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json({ error: { code: "unauthorized", message: "缺少或错误的 API Token，请在请求头加 Authorization: Bearer <token>" } }, { status: 401 });
  }
  return new NextResponse("需要登录", { status: 401, headers: { "WWW-Authenticate": 'Basic realm="video-review", charset="UTF-8"' } });
}

export const config = { matcher: "/((?!_next/static|favicon.ico).*)" };
