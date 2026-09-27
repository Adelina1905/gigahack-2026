// Model output and saved citations are untrusted. Only public web schemes link.
export function safeHttpUrl(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" && url.protocol !== "http:") return undefined;
    if (url.username || url.password) return undefined;
    const hostname = url.hostname.toLowerCase().replace(/^\[|\]$/g, "");
    const isIpv6 = hostname.includes(":");
    if (hostname === "localhost" || hostname.endsWith(".localhost") || hostname === "::1" ||
        (isIpv6 && (hostname.startsWith("fc") || hostname.startsWith("fd") || hostname.startsWith("fe80:")))) return undefined;
    const octets = hostname.split(".").map(Number);
    if (octets.length === 4 && octets.every(value => Number.isInteger(value) && value >= 0 && value <= 255)) {
      if (octets[0] === 0 || octets[0] === 10 || octets[0] === 127 ||
          (octets[0] === 100 && octets[1] >= 64 && octets[1] <= 127) ||
          (octets[0] === 169 && octets[1] === 254) ||
          (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) ||
          (octets[0] === 192 && octets[1] === 168)) return undefined;
    }
    return url.href;
  } catch {
    return undefined;
  }
}
