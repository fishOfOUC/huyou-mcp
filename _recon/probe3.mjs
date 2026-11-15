import { createHash } from "node:crypto";
const APP={appid:330012,app_key_vs:"6.24.0",app_key:"1U32034rUs20A064"},P_APPID="110503";
const BASE="https://cs-ol.sns.sohu.com";
const md5=s=>createHash("md5").update(s,"utf8").digest("hex");
const nonce=()=>{let r=Date.now().toString(16);while(r.length<32)r+=Math.random().toString(16).slice(2);return r.slice(0,32);};
function sign(input,headers){const out={...(input??{})};out.flyer=Date.now();out.appid=APP.appid;out.app_key_vs=APP.app_key_vs;const pairs=[];for(const k of Object.keys(out)){if(out[k]==null){delete out[k];continue}pairs.push(`${k}=${out[k]}`)}const n=headers["s-nonce"];if(n){pairs.push("s-nonce="+n);pairs.push("S-VS="+(headers["S-VS"]));}pairs.sort();pairs.push(APP.app_key);out.sig=md5(pairs.join(""));return out;}
function headers(){return {"Content-Type":"application/x-www-form-urlencoded","S-PID":"","S-PPID":"","S-VS":APP.app_key_vs,"S-CID":"",gid:"",token:"","P-APPID":P_APPID,appid:String(APP.appid),"s-nonce":nonce(),flyer:String(Date.now())};}
async function get(path,params){const h=headers();const q=sign(params,h);const url=BASE+path+"?"+new URLSearchParams(Object.entries(q).map(([k,v])=>[k,String(v)])).toString();const r=await fetch(url,{headers:h});return await r.json();}
const j=await get("/v8/circle/feed/list",{circle_id:"796893005792620800",tpl:"1,2,3,4,26,29",stpl:"1,2,3,4,7,9,11,12,13,16",count:3,withTop:1,score:0,list_type:2,extras:1});
import {writeFileSync} from "node:fs";
writeFileSync("_recon/sample_feeds.json",JSON.stringify(j,null,2),"utf8");
const f=(j.data.feedList[0].sourceFeed??j.data.feedList[0]);
console.log("ALL FIELDS:",Object.keys(f).sort().join(","));
console.log("\ncircle:",JSON.stringify(f.circle));
console.log("\ncontent:",JSON.stringify(f.content).slice(0,1500));
console.log("\nboardId:",f.boardId,"| type:",f.type,"| stpl:",f.stpl,"| commentCount:",f.commentCount,"| repostCount:",f.repostCount);
for (const k of ["publishTime","createTime","time","ctime","ptime","timestamp","lastUpdateTime","updateTime"]) if (k in f) console.log("timefield",k,"=",f[k], "->", new Date(Number(f[k])).toISOString());
console.log("\nfeedId:",f.feedId, "isTopFeed:", f.isTopFeed, "like fields:", Object.keys(f).filter(k=>/praise|like|up/i.test(k)).map(k=>k+"="+JSON.stringify(f[k]).slice(0,60)).join(" | "));
