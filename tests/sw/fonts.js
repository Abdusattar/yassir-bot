const fs=require('fs');
let src=fs.readFileSync('mushaf_data/sw.js','utf8').replace('const FONT_LIMIT = 150','const FONT_LIMIT = 5');
const O='https://y.test';
class Cache{constructor(){this.m=new Map()}
  async match(req){const u=typeof req==='string'?new URL(req,O).href:req.url;return this.m.has(u)?this.m.get(u).clone():undefined}
  async put(req,res){const u=typeof req==='string'?new URL(req,O).href:req.url;this.m.set(u,res)}
  async delete(req){return this.m.delete(typeof req==='string'?new URL(req,O).href:req.url)}
  async keys(){return [...this.m.keys()].map(u=>({url:u}))}}
const store={};const caches={open:async n=>store[n]||(store[n]=new Cache()),keys:async()=>Object.keys(store),delete:async n=>delete store[n],match:async()=>undefined};
let netLog=[];
const fetch=async(req)=>{netLog.push(new URL(req.url).pathname);return new Response('font',{status:200})};
const handlers={};const self={location:{origin:O},addEventListener:(n,f)=>handlers[n]=f,skipWaiting(){},clients:{claim(){}}};
let now=1000;const D={now:()=>now};
new Function('self','caches','fetch','URL','setTimeout','Response','Date',src)(self,caches,fetch,URL,setTimeout,Response,D);
async function get(path){let p;const w=[];const e={request:{method:'GET',url:path.startsWith('http')?path:O+path},respondWith:x=>p=x,waitUntil:x=>w.push(x)};handlers.fetch(e);const r=await p;await Promise.all(w);now+=10;return r}
const fonts=()=>[...store['yassir-fonts-v1'].m.keys()].filter(u=>/p\d+\.woff2/.test(u)).map(u=>u.match(/p(\d+)/)[1]).join(',');
const ok=(n,c,x)=>console.log(c?'OK  ':'FAIL',n,x||'');
(async()=>{
  for(let i=1;i<=5;i++)await get('/v4/p'+i+'.woff2');
  ok('5 шрифтов в кэше',fonts()==='1,2,3,4,5',fonts());
  await get('/v4/p1.woff2');                       // лист 1 открыли снова - он свежий
  netLog=[];await get('/v4/p6.woff2');
  ok('шестой вытеснил самый давний (2), а не открытый заново (1)',fonts()==='1,3,4,5,6',fonts());
  await get('/v4/p7.woff2');await get('/v4/p8.woff2');
  ok('дальше уходят 3 и 4',fonts()==='1,5,6,7,8',fonts());
  netLog=[];await get('/v4/p2.woff2');ok('вытесненный качается заново',netLog.length===1,fonts());
  await get('/fonts/ui.woff2');await get('https://cdn.test/x/p9.woff2');
  const all=[...store['yassir-fonts-v1'].m.keys()];
  ok('шрифт интерфейса не вытесняется и не считается',all.some(u=>u.endsWith('/fonts/ui.woff2')));
  ok('шрифт листа с чужого сервера считается',fonts().split(',').length===5&&fonts().includes('9'),fonts());
  const lru=JSON.parse(await (await store['yassir-fonts-v1'].match('/__font_lru')).text());
  ok('отметки только у тех, что в кэше',Object.keys(lru).length===5,Object.keys(lru).length);
  // 12 листов разом (предзагрузка)
  await Promise.all([20,21,22,23,24,25,26,27,28,29,30,31].map(i=>get('/v4/p'+i+'.woff2')));
  ok('разом 12 - остаётся предел',fonts().split(',').length===5,fonts());
})();
