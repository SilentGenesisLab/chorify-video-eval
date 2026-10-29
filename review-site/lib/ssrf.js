import dns from "node:dns/promises";
import net from "node:net";

// 服务端外发请求（files[].url 下载、callback_url 回调）的地址检查：
// 只允许公网地址；回环 / 内网 / 链路本地 / 保留地址一律拒绝，每一跳跳转都重新检查。
// SSRF_ALLOW_HOSTS：逗号分隔的 host:port，按 URL 里的 host:port 原样匹配，命中即放行（内网服务、测试辅助服务用）。

const blocked = new net.BlockList();
for (const [a, p] of [["0.0.0.0", 8], ["10.0.0.0", 8], ["100.64.0.0", 10], ["127.0.0.0", 8], ["169.254.0.0", 16],
  ["172.16.0.0", 12], ["192.0.0.0", 24], ["192.168.0.0", 16], ["198.18.0.0", 15], ["224.0.0.0", 3]]) {
  blocked.addSubnet(a, p, "ipv4");
}
for (const [a, p] of [["::", 128], ["::1", 128], ["fc00::", 7], ["fe80::", 10], ["ff00::", 8], ["64:ff9b::", 96], ["2001:db8::", 32]]) {
  blocked.addSubnet(a, p, "ipv6");
}

// ::ffff:7f00:1、::ffff:127.0.0.1 这类 IPv4 映射地址按其中的 IPv4 判断
function mappedV4(ip) {
  const m = /^::ffff:(?:(\d+\.\d+\.\d+\.\d+)|([0-9a-f]{1,4}):([0-9a-f]{1,4}))$/i.exec(ip);
  if (!m) return null;
  if (m[1]) return m[1];
  const hi = parseInt(m[2], 16), lo = parseInt(m[3], 16);
  return `${hi >> 8}.${hi & 255}.${lo >> 8}.${lo & 255}`;
}

export function isPrivateIp(ip) {
  const v4 = net.isIPv4(ip) ? ip : mappedV4(ip);
  if (v4) return blocked.check(v4, "ipv4");
  return net.isIPv6(ip) ? blocked.check(ip, "ipv6") : true;
}

const allowList = () => (process.env.SSRF_ALLOW_HOSTS || "").split(",").map((x) => x.trim().toLowerCase()).filter(Boolean);

function allowed(u) {
  const list = allowList();
  const port = u.port || (u.protocol === "https:" ? "443" : "80");
  return list.includes(u.host.toLowerCase()) || list.includes(`${u.hostname.toLowerCase()}:${port}`);
}

/** 地址可以外发时返回 URL 对象，否则返回 null。DNS 解析失败时 resolveFailOpen 决定是否放行（之后真正请求时还会再查）。 */
export async function checkUrl(raw, { resolveFailOpen = false } = {}) {
  let u;
  try {
    u = new URL(raw);
  } catch {
    return null;
  }
  if (!["http:", "https:"].includes(u.protocol) || u.username || u.password) return null;
  if (allowed(u)) return u;
  const host = u.hostname.replace(/^\[|\]$/g, "");
  if (net.isIP(host)) return isPrivateIp(host) ? null : u;
  let addrs;
  try {
    addrs = await dns.lookup(host, { all: true, verbatim: true });
  } catch {
    return resolveFailOpen ? u : null;
  }
  return addrs.length && addrs.every((a) => !isPrivateIp(a.address)) ? u : null;
}

/**
 * 按地址检查后请求，手动跟随跳转（每一跳重新检查）。
 * onBlocked(url) 在某一跳被拒绝时调用并应抛出错误。返回最终的 Response。
 */
export async function safeFetch(raw, init, onBlocked, maxRedirects = 5) {
  let url = raw;
  for (let i = 0; i <= maxRedirects; i++) {
    if (!(await checkUrl(url))) onBlocked(url);
    const r = await fetch(url, { ...init, redirect: "manual" });
    const loc = r.headers.get("location");
    if (![301, 302, 303, 307, 308].includes(r.status) || !loc) return r;
    await r.body?.cancel();
    url = new URL(loc, url).toString();
  }
  throw new Error("跳转次数过多");
}
