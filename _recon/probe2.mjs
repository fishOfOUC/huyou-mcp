import { createHash } from "node:crypto";
const APP={appid:330012,app_key_vs:"6.24.0",app_key:"1U32034rUs20A064"},P_APPID="110503";
const BASE="https://cs-ol.sns.sohu.com";
const md5=s=>createHash("md5").update(s,"utf8").digest("hex");
const nonce=()=>{let r=Date.now().toString(16);while(r.length<32)r+=Math.random().toString(16).slice(2);return r.slice(0,32);};
function sign(input,headers){const out={...(input??{})};if(out.sig)return out;out.flyer=Date.now();out.appid=APP.appid;out.app_key_vs=APP.app_key_vs;const pairs=[];for(const k of Object.keys(out)){if(out[k]==null){delete out[k];continue}pairs.push(`${k}=${out[k]}`)}const n=headers["s-nonce"];if(n){pairs.push("s-nonce="+n);pairs.push("S-VS="+(headers["S-VS"]??headers["s-vs"]))}pairs.sort();pairs.push(APP.app_key);out.sig=md5(pairs.join(""));return out;}
function headers(){return {"Content-Type":"application/x-www-form-urlencoded","S-PID":"","S-PPID":"","S-VS":APP.app_key_vs,"S-CID":"",gid:"",token:"","P-APPID":P_APPID,appid:String(APP.appid),"s-nonce":nonce(),flyer:String(Date.now())};}
async function get(path,params){const h=headers();const q=sign(params,h);const url=BASE+path+"?"+new URLSearchParams(Object.entries(q).map(([k,v])=>[k,String(v)])).toString();const r=await fetch(url,{headers:h});const j=await r.json();return {path,params,url,status:r.status,json:j};}
const circleId=process.argv[2]??"796893005792620800";
for (const cfg of [
  {label:"新发 list_type=2",p:{circle_id:circleId,tpl:"1,2,3,4,26,29",stpl:"1,2,3,4,7,9,11,12,13,16",count:20,withTop:1,score:0,list_type:2,extras:1}},
  {label:"热门 list_type=1",p:{circle_id:circleId,tpl:"1,2,3,4,26",stpl:"1,2,3,4,7,9,11,12,13,16",count:20,withTop:1,score:0,list_type:1,extras:1}},
]) {
  const r=await get("/v8/circle/feed/list",cfg.p);
  console.log("\n### "+cfg.label+" circle="+circleId);
  console.log(" status:",r.json.status,r.json.desc??"");
  const d=r.json.data??{};
  console.log(" keys:",Object.keys(d).join(","));
  const fl=d.feedList??[];
  console.log(" feedList:",fl.length, "pageInfo:",JSON.stringify(d.pageInfo));
  for (const raw of fl.slice(0,4)) {
    const f=raw.sourceFeed??raw;
    console.log("  - feedId:",f.feedId,"| user:",f.userName,"| uid:",f.userId,"| tpl/stpl:",f.tpl,f.stpl,"| time:",new Date(Number(f.publishTime??f.createTime??0)).toISOString());
    const text=(f.content?.text??f.text??JSON.stringify(f.content??"")).toString().replace(/\s+/g," ").slice(0,100);
    console.log("    text:",text);
    console.log("    keys:",Object.keys(f).slice(0,40).join(","));
  }
}
