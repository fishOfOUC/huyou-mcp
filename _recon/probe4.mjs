import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";
const APP={appid:330012,app_key_vs:"6.24.0",app_key:"1U32034rUs20A064"},P_APPID="110503";
const BASE="https://cs-ol.sns.sohu.com";
const md5=s=>createHash("md5").update(s,"utf8").digest("hex");
const nonce=()=>{let r=Date.now().toString(16);while(r.length<32)r+=Math.random().toString(16).slice(2);return r.slice(0,32);};
function sign(input,headers){const out={...(input??{})};if(out.sig)return out;out.flyer=Date.now();out.appid=APP.appid;out.app_key_vs=APP.app_key_vs;const pairs=[];for(const k of Object.keys(out)){if(out[k]==null){delete out[k];continue}pairs.push(`${k}=${out[k]}`)}const n=headers["s-nonce"];if(n){pairs.push("s-nonce="+n);pairs.push("S-VS="+headers["S-VS"]);}pairs.sort();pairs.push(APP.app_key);out.sig=md5(pairs.join(""));return out;}
function headers(cookies={}){return {"Content-Type":"application/x-www-form-urlencoded","S-PID":cookies.hyuid??"","S-PPID":cookies.pchypp??"","S-VS":APP.app_key_vs,"S-CID":cookies.gidinf??"",gid:cookies.gidinf??"",token:cookies.pchytk??"","P-APPID":P_APPID,appid:String(APP.appid),"s-nonce":nonce(),flyer:String(Date.now())};}
async function call(path,{method="GET",params={},cookies={}}={}){const h=headers(cookies);const q=sign(params,h);let url=BASE+path,body;if(method==="GET"){url+="?"+new URLSearchParams(Object.entries(q).map(([k,v])=>[k,String(v)])).toString();}else{body=new URLSearchParams(Object.entries(q).map(([k,v])=>[k,String(v)])).toString();}
 const ck=Object.entries(cookies).map(([k,v])=>`${k}=${v}`).join("; ");if(ck)h.Cookie=ck;
 const r=await fetch(url,{method,headers:h,body}); const t=await r.text(); let j=null; try{j=JSON.parse(t)}catch{}; return {http:r.status,setCookie:r.headers.getSetCookie?.()??[],json:j,text:t.slice(0,300),url};}

console.log("=== 1. QR login create ===");
const qr = await call("/v8/login/qrcode/create",{method:"POST"});
console.log("http:",qr.http,"| set-cookie:",qr.setCookie.map(c=>c.split(";")[0]).join(" ; "));
console.log("json:", JSON.stringify(qr.json).slice(0,300));
if (qr.json?.data?.codeBase64) {
  const b64 = qr.json.data.codeBase64.replace(/^data:image\/\w+;base64,/,"");
  writeFileSync("_recon/qr.png", Buffer.from(b64,"base64"));
  console.log("saved QR ->", "_recon/qr.png", (Buffer.from(b64,"base64").length/1024).toFixed(1)+" KB", "serialno:", qr.json.data.serialno);
}
const cookiesFromQr = Object.fromEntries(qr.setCookie.map(c=>{const [kv]=c.split(";");const i=kv.indexOf("=");return [kv.slice(0,i),kv.slice(i+1)]}));
console.log("cookies:", Object.keys(cookiesFromQr).join(","));

console.log("\n=== 2. QR poll (expect pending) ===");
const serialno = qr.json?.data?.serialno;
if (serialno) {
  const body = new URLSearchParams({serialno, appid:P_APPID, timestamp:String(Date.now()), gid:cookiesFromQr.gidinf??""}).toString();
  const r = await fetch("https://pol.passport.sohu.com/passportapi/polling/apptkbyhy",{method:"POST",credentials:"include",headers:{"Content-Type":"application/x-www-form-urlencoded",Cookie:Object.entries(cookiesFromQr).map(([k,v])=>`${k}=${v}`).join("; ")},body});
  const j = await r.json().catch(()=>null);
  console.log("poll http:",r.status,"json:",JSON.stringify(j).slice(0,300));
}

console.log("\n=== 3. feed detail /v7/feeds/show ===");
const det = await call("/v7/feeds/show",{params:{feed_id:"1497670320637805952"}});
console.log("status:", det.json?.status, det.json?.desc??"");
const d = det.json?.data ?? {};
console.log("keys:", Object.keys(d).join(","));
const sf = d.sourceFeed ?? {};
console.log("sourceFeed keys:", Object.keys(sf).sort().join(","));
for (const k of ["publishTime","createTime","time","timestamp","likeCount","likeStatus","commentCount","repostCount"]) if (k in sf) console.log("  ",k,"=",JSON.stringify(sf[k]));
if (sf.publishTime||sf.createTime) console.log("  time ->", new Date(Number(sf.publishTime??sf.createTime)).toISOString());

console.log("\n=== 4. comment list /v8/comment/list ===");
const cl = await call("/v8/comment/list",{params:{feed_id:"1497670320637805952",score:0,count:20,stpl:"1,2,4,7,8,9,16",source:1}});
console.log("status:", cl.json?.status, cl.json?.desc??"");
console.log("data keys:", Object.keys(cl.json?.data??{}).join(","));
const first = cl.json?.data?.commentList?.[0];
if (first) console.log("comment keys:", Object.keys(first).join(","), "\n sample:", JSON.stringify(first).slice(0,400));
