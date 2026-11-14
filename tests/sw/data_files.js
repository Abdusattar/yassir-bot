const fs=require('fs');
const src=fs.readFileSync('mushaf_data/sw.js','utf8');
const O='https://y.test';
class Cache{constructor(){this.m=new Map()}
  async match(req,o){const u=typeof req==='string'?new URL(req,O).href:req.url;
    if(this.m.has(u))return this.m.get(u).clone();
    if(o&&o.ignoreSearch){const p=new URL(u).pathname;for(const [k,v] of this.m)if(new URL(k).pathname===p)return v.clone();}
    return undefined}
  async put(req,res){const u=typeof req==='string'?new URL(req,O).href:req.url;this.m.set(u,res)}
  async delete(req){return this.m.delete(typeof req==='string'?req:req.url)}
  async keys(){return [...this.m.keys()].map(u=>({url:u}))}}
const store={};const caches={open:async n=>store[n]||(store[n]=new Cache()),keys:async()=>Object.keys(store),delete:async n=>delete store[n],
  match:async r=>{for(const c of Object.values(store)){const h=await c.match(r);if(h)return h}}};
let net={},netLog=[],offline=false,delay=0;
const mkRes=(body)=>({ok:true,body,clone(){return mkRes(body)}});
const fetch=async(req)=>{const u=req.url;netLog.push(u.replace(O,''));if(delay)await new Promise(r=>setTimeout(r,delay));
  if(offline)throw new Error('offline');const b=net[new URL(u).pathname];return b===undefined?{ok:false,clone(){return this}}:mkRes(b)};
const handlers={};const self={location:{origin:O},addEventListener:(n,f)=>handlers[n]=f,skipWaiting(){},clients:{claim(){}}};
new Function('self','caches','fetch','URL','setTimeout',src)(self,caches,fetch,URL,setTimeout);
async function get(path){let p;const e={request:{method:'GET',url:O+path},respondWith:x=>p=x};handlers.fetch(e);
  try{const r=await p;await new Promise(r=>setTimeout(r,20));return r&&r.ok?r.body:(r?'HTTP-ERR':'none')}catch(err){return 'REJECT'}}
const keys=async()=>store['yassir-pages-v1']?[...store['yassir-pages-v1'].m.keys()].map(u=>u.replace(O,'')):[];
const ok=(name,c)=>console.log((c?'OK  ':'FAIL'),name);
(async()=>{
  for(const base of ['/page5.json','/dm/page5.json','/meaning/ru_kuliev/2.json','/wbw/ru/2.json']){
    store['yassir-pages-v1']=new Cache();
    // прежняя оболочка положила запись без отпечатка
    net[base]='v1';netLog=[];offline=false;
    if(!base.startsWith('/dm')&&!base.startsWith('/wbw')){await get(base);ok(base+' без отпечатка кладётся в кэш',(await keys()).includes(base));}
    netLog=[];ok(base+' ?h=aa из сети',await get(base+'?h=aa')==='v1'&&netLog.length===1);
    ok(base+' одна запись на файл',JSON.stringify(await keys())===JSON.stringify([base+'?h=aa']));
    netLog=[];ok(base+' повтор без сети в запросах',await get(base+'?h=aa')==='v1'&&netLog.length===0);
    offline=true;ok(base+' офлайн из кэша',await get(base+'?h=aa')==='v1');
    ok(base+' офлайн, новый отпечаток -> прежняя версия',await get(base+'?h=bb')==='v1');
    if(!base.startsWith('/wbw'))ok(base+' офлайн без отпечатка -> запись с отпечатком',await get(base)==='v1');
    offline=false;net[base]='v2';
    ok(base+' новый отпечаток -> новое',await get(base+'?h=bb')==='v2');
    ok(base+' старая версия вытеснена',JSON.stringify(await keys())===JSON.stringify([base+'?h=bb']));
    if(!base.startsWith('/wbw')){netLog=[];const r=await get(base);ok(base+' без отпечатка при записи с отпечатком: из кэша, второй копии нет',r==='v2'&&(await keys()).length===1);}
  }
  for(const man of ['/data_manifest.json','/wbw/manifest.json']){
    store['yassir-pages-v1']=new Cache();net[man]='m1';offline=false;delay=0;
    ok(man+' из сети',await get(man)==='m1');
    net[man]='m2';ok(man+' сеть вперёд',await get(man)==='m2');
    offline=true;ok(man+' офлайн -> последний',await get(man)==='m2');
    offline=false;net[man]='m3';delay=1600;const t=Date.now();const r=await get(man);const dt=Date.now()-t;
    ok(man+' медленная сеть -> последний через ~1 с ('+dt+' мс)',r==='m2'&&dt<1300);
    await new Promise(r=>setTimeout(r,800));delay=0;offline=true;ok(man+' свежий доехал в кэш',await get(man)==='m3');
    store['yassir-pages-v1']=new Cache();ok(man+' офлайн и пусто -> ошибка, не зависание',await get(man)==='REJECT');offline=false;
  }
  net['/api/muf/x']='live';let called=false;handlers.fetch({request:{method:'GET',url:O+'/api/muf/x'},respondWith:()=>called=true});ok('api мимо',!called);
})();
