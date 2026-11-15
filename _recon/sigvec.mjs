import { createHash } from "node:crypto";
function jsStr(v){ if(typeof v==="boolean") return v?"true":"false"; return String(v); }
function sign(params, headers, nowMs){
  const out = {...params};
  out.flyer = nowMs; out.appid = 330012; out.app_key_vs = "6.24.0";
  const u = [];
  for (const k of Object.keys(out)) { if (out[k] == null) { delete out[k]; continue; } u.push(k + "=" + jsStr(out[k])); }
  if (headers["s-nonce"]) { u.push("s-nonce=" + headers["s-nonce"]); u.push("S-VS=" + (headers["S-VS"] ?? headers["s-vs"])); }
  u.sort(); u.push("1U32034rUs20A064");
  out.sig = createHash("md5").update(u.join(""), "utf8").digest("hex");
  return {out, signed: u.join("|")};
}
const a = sign({circle_id:"796893005792620800", count:20, tpl:"1,2,3,4,26"}, {"s-nonce":"abc123","S-VS":"6.24.0"}, 1794717000000);
console.log("VECTOR1 sig:", a.out.sig);
console.log("VECTOR1 signed:", a.signed);
const b = sign({feed_id:"1497670320637805952", count:20}, {"s-nonce":"deadbeef","S-VS":"6.24.0"}, 1794718000123);
console.log("VECTOR2 sig:", b.out.sig);
console.log("VECTOR2 signed:", b.signed);
