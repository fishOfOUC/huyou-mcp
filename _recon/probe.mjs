// 狐友 Web API 探测脚本（逆向自 hy.cdn.sohucs.com 前端 bundle）
// 目的：确认只读内容接口是否可在不带登录态 / 带登录态下调用
import { createHash } from 'node:crypto';

const APP = { appid: 330012, app_key_vs: '6.24.0', app_key: '1U32034rUs20A064' };
const P_APPID = '110503';
const BASES = {
  cs: 'https://cs-ol.sns.sohu.com',
  op: 'https://op-ol.sns.sohu.com',
  dm: 'https://dm-ol.sns.sohu.com',
};

const md5 = (s) => createHash('md5').update(s, 'utf8').digest('hex');

function nonce() {
  let r = Date.now().toString(16);
  while (r.length < 32) r += Math.random().toString(16).slice(2);
  return r.slice(0, 32);
}

// 对应前端 Hi(body, Nn, 0, headers)
function signParams(input, headers) {
  const out = { ...(input ?? {}) };
  if (out.sig) return out;
  out.flyer = Date.now();
  out.appid = APP.appid;
  out.app_key_vs = APP.app_key_vs;
  const pairs = [];
  for (const k of Object.keys(out)) {
    if (out[k] == null) { delete out[k]; continue; }
    pairs.push(`${k}=${out[k]}`);
  }
  const n = headers['s-nonce'];
  if (n) {
    pairs.push(`s-nonce=${n}`);
    pairs.push(`S-VS=${headers['S-VS'] ?? headers['s-vs']}`);
  }
  pairs.sort();
  pairs.push(APP.app_key);
  out.sig = md5(pairs.join(''));
  return out;
}

function buildHeaders(cookies = {}) {
  return {
    'Content-Type': 'application/x-www-form-urlencoded',
    'S-PID': cookies.hyuid ?? '',
    'S-PPID': cookies.pchypp ?? '',
    'S-VS': APP.app_key_vs,
    'S-CID': cookies.gidinf ?? '',
    gid: cookies.gidinf ?? '',
    token: cookies.pchytk ?? '',
    'P-APPID': P_APPID,
    appid: String(APP.appid),
    's-nonce': nonce(),
    flyer: String(Date.now()),
  };
}

async function call(base, path, { method = 'GET', params = {}, cookies = {}, signed = true } = {}) {
  const headers = buildHeaders(cookies);
  let url = `${BASES[base]}${path}`;
  let body;
  if (signed) {
    if (method === 'GET') {
      const q = signParams(params, headers);
      url += '?' + new URLSearchParams(Object.entries(q).map(([k, v]) => [k, String(v)])).toString();
    } else {
      body = new URLSearchParams(Object.entries(signParams(params, headers)).map(([k, v]) => [k, String(v)])).toString();
    }
  } else if (method === 'GET') {
    url += '?' + new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
  } else {
    body = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
  }
  const cookieStr = Object.entries(cookies).map(([k, v]) => `${k}=${v}`).join('; ');
  if (cookieStr) headers.Cookie = cookieStr;
  const res = await fetch(url, { method, headers, body, redirect: 'follow' });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch {}
  return { url, httpStatus: res.status, setCookie: res.headers.getSetCookie?.() ?? [], json, text: text.slice(0, 600) };
}

const show = (label, r) => {
  console.log(`\n### ${label}`);
  console.log('   url:', r.url.slice(0, 160));
  console.log('   http:', r.httpStatus, r.setCookie.length ? 'set-cookie: ' + r.setCookie.map((c) => c.split(';')[0]).join(', ') : '');
  if (r.json) {
    console.log('   status:', r.json.status, '| desc:', r.json.desc ?? r.json.msg ?? '');
    const d = r.json.data ?? r.json;
    if (d && typeof d === 'object') {
      console.log('   data keys:', Object.keys(d).slice(0, 12).join(','));
      if (Array.isArray(d.circleList)) {
        console.log('   circleList count:', d.circleList.length);
        d.circleList.slice(0, 5).forEach((c) => console.log('     -', c.circleId, c.circleName, 'feeds:', c.feedCount));
      }
      if (Array.isArray(d.feedList)) {
        console.log('   feedList count:', d.feedList.length);
        d.feedList.slice(0, 3).forEach((f) => {
          const sf = f.sourceFeed ?? f;
          console.log('     -', sf.feedId, '|', (sf.userName ?? '').slice(0, 20), '|', String(sf.content?.text ?? sf.content ?? '').replace(/\s+/g, ' ').slice(0, 60));
        });
      }
    }
  } else {
    console.log('   raw:', r.text.replace(/\s+/g, ' ').slice(0, 200));
  }
};

const which = process.argv[2] ?? 'all';

if (which === 'all' || which === 'public') {
  show('A1 /v9/circle/category/list (cs, unsigned)', await call('cs', '/v9/circle/category/list', { params: {}, signed: false }));
  show('A2 /v9/category/circle/list (cs, unsigned)', await call('cs', '/v9/category/circle/list', { params: { category_type: 2, score: 0, count: 20 }, signed: false }));
  show('A3 /v9/category/circle/list (cs, SIGNED)', await call('cs', '/v9/category/circle/list', { params: { category_type: 2, score: 0, count: 20 }, signed: true }));
  show('A4 /v9/category/circle/list (op, SIGNED)', await call('op', '/v9/category/circle/list', { params: { category_type: 2, score: 0, count: 20 }, signed: true }));
  show('A5 /v8/circle/feed/list (cs, SIGNED, no login)', await call('cs', '/v8/circle/feed/list', {
    params: { circle_id: '4', board_id: undefined, tpl: '1,2,3,4,26', stpl: '1,2,3,4,7,9,11,12,13,16', count: 20, withTop: 1, score: 0, list_type: 2, extras: 1 },
    signed: true,
  }));
}
