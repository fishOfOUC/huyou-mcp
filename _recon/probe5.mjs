import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";
const APP={appid:330012,app_key_vs:"6.24.0",app_key:"1U32034rUs20A064"},P_APPID="110503";
const BASE="https://cs-ol.sns.sohu.com";
const md5=s=>createHash("md5").update(s,"utf8").digest("hex");
const nonce=()=>{let r=Date.now().toString(16);while(r.length<32)r+=Math.random().toString(16).slice(2);return r.slice(0,32);};
function sign(input,headers){const out={...(input??{})};if(out.sig)return out;out.flyer=Date.now();out.appid=APP.appid;out.app_key_vs=APP.app_key_vs;const pairs=[];for(const k of Object.keys(out)){if(out[k]==null){delete out[k];continue}pairs.push(`${k}=${out[k]}`)}const n=headers["s-nonce"];if(n){pairs.push("s-nonce="+n);pairs.push("S-VS="+headers["S-VS"]);}pairs.sort();pairs.push(APP.app_key);out.sig=md5(pairs.join(""));return out;}
let jar={};
function setCookies(res){for(const c of res.headers.getSetCookie?.()??[]){const [kv]=c.split(";");const i=kv.indexOf("=");jar[kv.slice(0,i)]=kv.slice(i+1);}}
const jarStr=()=>Object.entries(jar).map(([k,v])=>`${k}=${v}`).join("; ");
function headers(){return {"Content-Type":"application/x-www-form-urlencoded","S-PID":jar.hyuid??"","S-PPID":jar.pchypp??"","S-VS":APP.app_key_vs,"S-CID":jar.gidinf??"",gid:jar.gidinf??"",token:jar.pchytk??"","P-APPID":P_APPID,appid:String(APP.appid),"s-nonce":nonce(),flyer:String(Date.now())};}
async function call(path,{method="GET",params={},base=BASE}={}){const h=headers();const q=sign(params,h);let url=base+path,body;if(method==="GET"){url+="?"+new URLSearchParams(Object.entries(q).map(([k,v])=>[k,String(v)])).toString();}else{body=new URLSearchParams(Object.entries(q).map(([k,v])=>[k,String(v)])).toString();}
 if(jarStr())h.Cookie=jarStr();
 const r=await fetch(url,{method,headers:h,body}); setCookies(r); const t=await r.text(); let j=null; try{j=JSON.parse(t)}catch{}; return {http:r.status,json:j,text:t.slice(0,300),url};}

console.log("=== step0: bootstrap gidinf from passport ===");
const p = await fetch("https://passport.sohu.com", {headers:{"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0 Safari/537.36"}});
setCookies(p);
console.log("http:",p.status,"| jar:",Object.keys(jar).join(","));

console.log("\n=== step1: QR create ===");
const qr = await call("/v8/login/qrcode/create",{method:"POST"});
console.log("http:",qr.http,"| json:",JSON.stringify(qr.json).slice(0,200));
console.log("jar now:",Object.keys(jar).join(","));
const data = qr.json?.data;
if (data?.codeBase64) {
  const b64 = data.codeBase64.replace(/^data:image\/\w+;base64,/,"");
  writeFileSync("_recon/qr.png", Buffer.from(b64,"base64"));
  console.log("QR saved -> _recon/qr.png serialno:", data.serialno);
  console.log("\n=== step2: poll once ===");
  const body = new URLSearchParams({serialno:data.serialno, appid:P_APPID, timestamp:String(Date.now()), gid:jar.gidinf??""}).toString();
  const r = await fetch("https://pol.passport.sohu.com/passportapi/polling/apptkbyhy",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded",Cookie:jarStr()},body});
  console.log("poll http:",r.status,"| body:",(await r.text()).slice(0,200));
}

console.log("\n=== step3: comment list structure ===");
const cl = await call("/v8/comment/list",{params:{feed_id:"1497670320637805952",score:0,count:20,stpl:"1,2,4,7,8,9,16",source:1}});
const list = cl.json?.data?.list ?? [];
console.log("status:",cl.json?.status,"| count:",list.length);
if (list[0]) { console.log("keys:",Object.keys(list[0]).join(",")); console.log("sample:",JSON.stringify(list[0]).slice(0,500)); }
