import { createHash } from "node:crypto";
const APP={appid:330012,app_key_vs:"6.24.0",app_key:"1U32034rUs20A064"},P_APPID="110503";
const BASE="https://cs-ol.sns.sohu.com";
const md5=s=>createHash("md5").update(s,"utf8").digest("hex");
const nonce=()=>{let r=Date.now().toString(16);while(r.length<32)r+=Math.random().toString(16).slice(2);return r.slice(0,32);};
function sign(input,headers){const out={...(input??{})};if(out.sig)return out;out.flyer=Date.now();out.appid=APP.appid;out.app_key_vs=APP.app_key_vs;const pairs=[];for(const k of Object.keys(out)){if(out[k]==null){delete out[k];continue}pairs.push(`${k}=${out[k]}`)}const n=headers["s-nonce"];if(n){pairs.push("s-nonce="+n);pairs.push("S-VS="+headers["S-VS"]);}pairs.sort();pairs.push(APP.app_key);out.sig=md5(pairs.join(""));return out;}
function headers(){return {"Content-Type":"application/x-www-form-urlencoded","S-PID":"","S-PPID":"","S-VS":APP.app_key_vs,"S-CID":"",gid:"",token:"","P-APPID":P_APPID,appid:String(APP.appid),"s-nonce":nonce(),flyer:String(Date.now())};}
async function get(path,params,extraHeaders={}){const h={...headers(),...extraHeaders};const q=sign(params,h);const url=BASE+path+"?"+new URLSearchParams(Object.entries(q).map(([k,v])=>[k,String(v)])).toString();const r=await fetch(url,{headers:h});const j=await r.json().catch(()=>null);return {status:r.status,json:j};}

const s = await get("/v8/circle/suggest/search",{query:"政法",page_index:1});
console.log("circle search:", s.json?.status, s.json?.desc ?? "", "| data keys:", Object.keys(s.json?.data??{}).join(","));
const cand = s.json?.data?.circleList ?? s.json?.data?.list ?? [];
console.log("results:", cand.length); cand.slice(0,5).forEach(c=>console.log("  -", c.circleId ?? c.id, c.circleName ?? c.name, c.feedCount ?? c.userCount));

const el = await get("/v8/circle/feed/list",{circle_id:"796893005792620800",tpl:"1,2,3,4,26",stpl:"1,2,3,4,7,9,11,12,13,16",count:20,withTop:1,score:0,list_type:3,extras:1});
const fl = el.json?.data?.feedList ?? [];
console.log("\nelite list:", el.json?.status, "count:", fl.length);
let withPic = 0;
for (const raw of fl) { const f = raw.sourceFeed ?? raw; if (f.picFeed) { withPic++; if (withPic <= 2) console.log("  picFeed keys:", Object.keys(f.picFeed).join(","), "\n   sample:", JSON.stringify(f.picFeed).slice(0,600)); } }
console.log("feeds with picFeed:", withPic, "/", fl.length);
console.log("sample stpl values:", [...new Set(fl.map(r=>(r.sourceFeed??r).stpl))].join(","));
