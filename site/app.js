"use strict";
/* NFL Edge dashboard. Reads site/data/*.json; no build step. */
const UNITS=[["off","Offense"],["pass","Pass O"],["rush","Rush O"],["qb","QB"],["def","Defense"],["passD","Pass D"],["rushD","Rush D"],["st","Spec. teams"],["pace","Pace"],["ovr","Overall"]];
const BOOK={draftkings:"DraftKings",fanduel:"FanDuel",bovada:"Bovada"};
const RANK={pass:0,model:1,lean:2,strong:3,lock:4};
const TABS=["week","schedule","matchup","lines","results","grades","compare"];
let G=null,S=null,P=null,I=null,W=null,TEAMS={},cur=null,loaded=false;
let slateF="all",slateQ="",schedF="all",schedQ="",sortK="ovr",sortDir=-1,tab="week";

const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const gcol=v=>`hsl(${Math.max(0,Math.min(1,(v-3)/6))*130} 62% 55%)`;
const chip=v=>v==null?"–":`<span class="gchip" style="background:${gcol(v)}">${v.toFixed(1)}</span>`;
const fmt=x=>x==null?"–":x===0?"PK":(x>0?"+":"")+(+x.toFixed(1));
const fmtP=p=>p==null?"–":(p>0?"+":"")+p;
const price=p=>p==null?"":` <span class="sub">(${fmtP(p)})</span>`;
const fmtT=x=>x==null?"–":+(+x).toFixed(1);
const short=n=>n.length>14?n.split(" ")[0]:n;
const tierName=t=>t==="lock"?"LOCK":t==="strong"?"Strong":t==="lean"?"Lean":t==="model"?"Model lean":"Pass";
const LOCK_ICON=`<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 10V7a5 5 0 0 1 10 0v3h1a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h1zm2 0h6V7a3 3 0 0 0-6 0v3z"/></svg>`;
const CLOCK=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`;
const pill=t=>`<span class="badge b-${t||"pass"}">${t==="lock"?LOCK_ICON:""}${tierName(t)}</span>`;
const valid=iso=>iso&&!isNaN(new Date(iso));
const when=(iso,o)=>valid(iso)?new Date(iso).toLocaleString([],o||{weekday:"short",hour:"numeric",minute:"2-digit"}):"–";
const kick=iso=>when(iso,{weekday:"short",month:"short",day:"numeric",hour:"numeric",minute:"2-digit",timeZoneName:"short"});
const tzName=(()=>{try{return new Intl.DateTimeFormat([],{timeZoneName:"short"}).formatToParts(new Date()).find(p=>p.type==="timeZoneName")?.value||""}catch(e){return ""}})();
const started=g=>valid(g.start)&&new Date(g.start)<=Date.now();
const rtf=(()=>{try{return new Intl.RelativeTimeFormat([],{numeric:"auto"})}catch(e){return null}})();
function rel(iso){
  if(!valid(iso))return "–";
  const s=(new Date(iso)-Date.now())/1000,a=Math.abs(s);
  if(a<60)return "just now";
  const [v,u]=a<3600?[s/60,"minute"]:a<86400?[s/3600,"hour"]:[s/86400,"day"];
  return rtf?rtf.format(Math.round(v),u):`${Math.round(Math.abs(v))} ${u}s ago`;
}
function relShort(iso){if(!valid(iso))return "–";const m=Math.round((Date.now()-new Date(iso))/6e4);
  return m<1?"Just now":m<60?`${m}m ago`:m<1440?`${Math.round(m/60)}h ago`:`${Math.round(m/1440)}d ago`;}
const timeTag=(iso,txt)=>`<time datetime="${esc(iso)}" title="${esc(when(iso,{dateStyle:"medium",timeStyle:"short"}))}">${esc(txt)}</time>`;
const cons=(g,k)=>{const v=Object.values(g.lines||{}).map(b=>b[k]).filter(x=>x!=null);return v.length?v.reduce((a,b)=>a+b)/v.length:null};
const favText=(g,s)=>s==null?"No line":s===0?"PK":s<0?`${g.home} ${fmt(s)}`:`${g.away} ${fmt(-s)}`;
const tier=g=>g.best?.tier||"pass";
const matchQ=(g,q)=>!q||`${g.away} ${g.home}`.toLowerCase().includes(q);
const color=t=>TEAMS[t]?.color||"var(--text-3)";
const gameHref=id=>`#/matchup/${encodeURIComponent(id)}`;
const full=t=>TEAMS[t]?.name||t;
const PATTERN={wind15:"Wind 15+ mph Under",wind10:"Wind 10-14 mph Under",playoff_dog:"Playoff underdog"};
const wxChip=g=>{const w=g.weather;if(!w||w.wind==null)return g.roof&&g.roof!=="outdoors"?`<span class="wx">${esc(g.roof==="neutral site"?"Neutral site":g.roof==="dome"?"Dome":"Roof")}</span>`:"";
  return `<span class="wx${w.wind>=10?" windy":""}" title="${esc(`NWS forecast for kickoff: ${w.wind_text||w.wind+" mph"} wind, ${w.temp??"?"}°F, ${w.short||""}`)}">💨 ${Math.round(w.wind)} mph</span>`;};
const edgeTxt=p=>p.pattern?`${esc(PATTERN[p.pattern]||p.pattern)}`:`${p.edge.toFixed(1)} pts`;

function pickPrice(g,p){
  const l=g.lines?.[p.book];if(!l)return null;
  if(p.bet==="spread")return p.side===g.home?l.spread_home_price:l.spread_away_price;
  return p.side==="Over"?l.over_price:l.under_price;
}
function oneLine(g,p){
  const s=g.why?.[p.bet]?.summary;
  if(s){const first=s.split(/(?<=\.)\s+(?=[A-Z])/)[0];return first;}
  const pr=g.projection||{};
  return p.bet==="spread"?`The model makes it ${favText(g,pr.spread)}; the market has ${favText(g,cons(g,"spread_home"))}.`
    :`The model projects ${pr.total} total points against a market of ${fmtT(cons(g,"total"))}.`;
}
function allPicks(){
  if(!S)return [];
  return S.games.flatMap(g=>["spread","total"].map(b=>g.picks?.[b]?{g,p:g.picks[b]}:null)).filter(Boolean);
}

/* ---------- tabs & routing ---------- */
function show(t,focus){
  if(!TABS.includes(t))t="week";tab=t;
  document.querySelectorAll(".tab").forEach(b=>{const on=b.dataset.tab===t;b.setAttribute("aria-selected",on);b.tabIndex=on?0:-1;
    if(on)b.scrollIntoView({block:"nearest",inline:"nearest"});});
  document.querySelectorAll("main .view").forEach(s=>s.hidden=s.id!=="v-"+t);
  try{localStorage.setItem("ne-tab",t)}catch(e){}
  const title={week:"This week's plays",schedule:"Schedule",matchup:"Matchup",lines:"Lines",results:"Results",grades:"Team grades",compare:"Compare"}[t];
  document.title=`${title} · NFL Edge`;
  if(focus)$("v-"+t).focus({preventScroll:true});
}
function hashFor(t){
  if(t==="matchup"&&cur)return gameHref(cur);
  if(t==="compare"&&$("away").value&&$("home").value)return `#/compare/${encodeURIComponent($("away").value)}/${encodeURIComponent($("home").value)}`;
  return "#/"+t;
}
function go(t){const h=hashFor(t);if(location.hash!==h)location.hash=h;else route();}
function setHashQuiet(h){if(location.hash!==h)history.replaceState(null,"",h);}
function route(e){
  const parts=location.hash.replace(/^#\/?/,"").split("/").filter(Boolean).map(s=>{try{return decodeURIComponent(s)}catch(x){return s}});
  let t=parts[0]==="slate"?"week":parts[0];
  if(!TABS.includes(t)){t="week";try{const s=localStorage.getItem("ne-tab");if(TABS.includes(s))t=s}catch(x){}}
  if(t==="matchup"&&parts[1]){cur=parts[1];if(loaded)renderMatchup();}
  if(t==="compare"&&parts[2]&&loaded&&TEAMS[parts[1]]&&TEAMS[parts[2]]){$("away").value=parts[1];$("home").value=parts[2];renderCompare();}
  const fromNav=!!e;
  show(t,false);
  if(fromNav){window.scrollTo({top:0});
    if(t==="matchup"&&parts[1]){const h=document.querySelector("#matchup .mtitle");if(h)h.focus({preventScroll:true});}}
}

/* ---------- status line ---------- */
function renderStatus(){
  const el=$("status");
  if(!loaded){return;}
  if(!S&&!G){el.innerHTML=`<span class="live stale" aria-hidden="true"></span><span>Data unavailable</span>`;return;}
  const u=S?.updated||G?.updated, ageH=(Date.now()-new Date(u))/36e5;
  const news=S?.news_checked&&valid(S.news_checked)?` · News checked ${timeTag(S.news_checked,rel(S.news_checked))}`:"";
  el.innerHTML=`<span class="live${ageH>12?" stale":""}" aria-hidden="true"></span>
    <span class="status-short">${timeTag(u,relShort(u))}</span>
    <span class="status-long">${S?"Lines updated":"Grades updated"} <b>${timeTag(u,rel(u))}</b>${news}</span>`;
  $("footUpdated").innerHTML=[S&&`Lines scanned ${timeTag(S.updated,when(S.updated,{dateStyle:"medium",timeStyle:"short"}))}`,
    S?.news_checked&&valid(S.news_checked)&&`News checked ${timeTag(S.news_checked,rel(S.news_checked))}`,
    G&&`Grades through Week ${G.through_week}, updated ${timeTag(G.updated,rel(G.updated))}`].filter(Boolean).join(" · ");
}

/* ---------- hero: this week's plays ---------- */
function playCard({g,p}){
  const pr=pickPrice(g,p),done=started(g);
  return `<a class="play t-${p.tier}" href="${gameHref(g.id)}" aria-label="${esc(`${tierName(p.tier)}: ${p.label}, ${g.away} at ${g.home}. ${p.pattern?PATTERN[p.pattern]:`Edge ${p.edge.toFixed(1)} points`} at ${BOOK[p.book]||p.book}. Open the full breakdown.`)}">
    <div class="play-top">${pill(p.tier)}<span class="kick">${CLOCK}${done?`<span class="badge b-live">Kicked off</span>`:timeTag(g.start,kick(g.start))}</span></div>
    <div><div class="play-pick">${esc(p.label)}</div></div>
    <div class="play-game">${esc(g.away)} @ ${esc(g.home)} · ${p.bet==="spread"?"Spread":"Total"} ${wxChip(g)}</div>
    <dl class="play-stats">
      <div><dt>${p.pattern?"Pattern":"Edge"}</dt><dd class="edge">${p.pattern?(p.wind!=null?`Wind ${Math.round(p.wind)} mph`:"Playoff dog"):`${p.edge.toFixed(1)} pts`}</dd></div>
      ${p.cover!=null?`<div><dt>${p.pattern?"Hist. win":"Covers"}</dt><dd title="${p.pattern?"How this pattern has done against the closing line since 1999.":"Estimated chance to win."} You need 52.4% to break even at -110.">${(p.cover*100).toFixed(1)}%</dd></div>`:""}
      <div><dt>Book</dt><dd>${esc(BOOK[p.book]||p.book)}</dd></div>
      <div><dt>Price</dt><dd>${fmtP(pr)}</dd></div>
    </dl>
    <p class="play-why">${esc(oneLine(g,p))}</p>
    ${p.note?`<p class="play-note">${esc(p.note)}</p>`:""}
    <span class="play-cta" aria-hidden="true">See why it qualifies →</span>
  </a>`;
}
function emptyCard(title,body){
  return `<div class="empty-card" role="note"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg><div><b>${title}</b><p>${body}</p></div></div>`;
}
function renderHero(){
  const el=$("hero");el.removeAttribute("aria-busy");
  if(!S){el.innerHTML=`<div class="hero-head"><div><p class="eyebrow">This week</p><h1>This week's plays</h1></div></div>`+
    emptyCard("No lines yet","Plays appear here after the first line scan of the week. Books post next week's lines on Sunday night.");return;}
  const picks=allPicks(),byEdge=(a,b)=>(started(a.g)-started(b.g))||String(a.g.start).localeCompare(String(b.g.start));
  const locks=picks.filter(x=>x.p.tier==="lock").sort(byEdge),strong=picks.filter(x=>x.p.tier==="strong").sort(byEdge);
  const leanL=picks.filter(x=>x.p.tier==="lean").sort(byEdge),leans=leanL.length,models=picks.filter(x=>x.p.tier==="model").length;
  el.innerHTML=`<div class="hero-head">
      <div><p class="eyebrow">Week ${esc(S.week??"")} · ${esc(G?.season??"")} season</p><h1>This week's plays</h1>
      <p class="sub">Games that match a pattern that has beaten the NFL closing line for decades, at the best DraftKings, FanDuel or Bovada number. Kickoffs are in your time zone${tzName?` (${esc(tzName)})`:""}.</p></div>
      <div class="stats" aria-label="This week at a glance">
        <div class="stat"><b class="num">${locks.length}</b><span>LOCK</span></div>
        <div class="stat"><b class="num">${strong.length}</b><span>Strong</span></div>
        <div class="stat"><b class="num">${leans}</b><span>Lean</span></div>
        <div class="stat"><b class="num">${models}</b><span>Model</span></div>
      </div></div>
    <div class="group"><h2 class="group-title">${pill("lock")} plays <span class="ct">${locks.length?`${locks.length} this week`:""}</span></h2>
      ${locks.length?`<div class="plays">${locks.map(playCard).join("")}</div>`:
        emptyCard("No LOCKs right now","A LOCK is an Under at an outdoor stadium with a forecast of 15+ mph wind, read within 36 hours of kickoff. Since 1999 those went 384-290 (57%). Most weeks have one or none, and they usually appear Saturday night once Sunday's forecast firms up.")}
    </div>
    <div class="group"><h2 class="group-title">${pill("strong")} plays <span class="ct">${strong.length?`${strong.length} this week, biggest edge first`:""}</span></h2>
      ${strong.length?`<div class="plays">${strong.map(playCard).join("")}</div>`:
        emptyCard("No Strong plays","Strong is a playoff underdog the model also likes, or a 15+ mph wind Under whose kickoff is still more than 36 hours away.")}
    </div>
    <div class="group"><h2 class="group-title">${pill("lean")} plays <span class="ct">${leans?`${leans} this week`:""}</span></h2>
      ${leans?`<div class="plays">${leanL.map(playCard).join("")}</div>`:
        emptyCard("No Leans","A Lean is an Under at an outdoor stadium with a 10-14 mph wind forecast (650-558 since 1999, 53.8%).")}
    </div>
    <details class="legend"><summary>How to read these tiers</summary><div class="legend-body">
      <dl><dt>${pill("lock")}</dt><dd>Under at an outdoor stadium, forecast wind 15+ mph, forecast read within 36 hours of kickoff. 384-290 (57.0%) since 1999, profitable in 17 of 27 seasons. Our highest tier, not a guarantee.</dd>
      <dt>${pill("strong")}</dt><dd>Playoff underdog the model also likes: 136-109 (55.5%). Or a 15+ mph wind Under more than 36 hours before kickoff.</dd>
      <dt>${pill("lean")}</dt><dd>Under at an outdoor stadium with a 10-14 mph wind forecast: 650-558 (53.8%), profitable in 16 of 28 seasons.</dd>
      <dt>${pill("model")}</dt><dd>The model disagrees with the best line by 3+ points. Unproven: in 27 seasons of replays these won about 50%.</dd>
      <dt>${pill("pass")}</dt><dd>No pattern, and the model and the market roughly agree.</dd></dl>
      <p>Records are against the closing line, at -110, where 52.4% breaks even. Price is the book's odds when we last scanned. Wind is the National Weather Service forecast for kickoff. Check the injury report before betting.</p>
    </div></details>`;
}

/* ---------- all games ---------- */
function pickBox(label,g,p){
  if(!p)return `<div class="pk"><span class="label">${label}</span><b class="muted">No line yet</b><span class="e">–</span></div>`;
  return `<div class="pk"><span class="label">${label}</span><b>${esc(p.label)}</b><span class="e">${pill(p.tier)} ${edgeTxt(p)} · ${BOOK[p.book]||p.book}</span></div>`;
}
function renderSlate(){
  if(!S){$("slate").innerHTML=`<p class="empty">Games appear after the first line scan of the week.</p>`;return;}
  const list=S.games.filter(g=>{const t=tier(g);
    return matchQ(g,slateQ)&&(slateF==="lock"?t==="lock":slateF==="strong"?RANK[t]>=3:slateF==="lean"?RANK[t]>=2:slateF==="model"?Object.values(g.picks||{}).some(p=>p&&p.tier==="model"):slateF==="lines"?Object.keys(g.lines||{}).length>0:true);})
    .sort((a,b)=>(started(a)-started(b))||(RANK[tier(b)]-RANK[tier(a)])||(b.best?.edge||0)-(a.best?.edge||0));
  $("slateCount").textContent=`${list.length} game${list.length===1?"":"s"} shown`;
  $("slate").innerHTML=list.map(g=>{const s=cons(g,"spread_home"),t=cons(g,"total"),A=TEAMS[g.away],H=TEAMS[g.home];
    return `<a class="game t-${tier(g)}" href="${gameHref(g.id)}">
      <div class="gmeta"><span>${started(g)?`<span class="badge b-live">Kicked off</span>`:timeTag(g.start,kick(g.start))}</span><span>${wxChip(g)}${g.type&&g.type!=="REG"?" · Playoffs":""}</span></div>
      <div class="teams" aria-label="Model projected score">
        <span class="swatch" style="background:${color(g.away)}"></span><span class="tn">${esc(g.away)}${A?`<small>${esc(A.record)}</small>`:""}</span><span class="proj">${g.projection?.away??"–"}</span>
        <span class="swatch" style="background:${color(g.home)}"></span><span class="tn">@ ${esc(g.home)}${H?`<small>${esc(H.record)}</small>`:""}</span><span class="proj">${g.projection?.home??"–"}</span></div>
      <div class="gmeta"><span>Market <b class="num">${esc(favText(g,s))}</b> · O/U <b class="num">${fmtT(t)}</b></span><span>Model score</span></div>
      <div class="picks2">${pickBox("Spread",g,g.picks?.spread)}${pickBox("Total",g,g.picks?.total)}</div></a>`}).join("")
    ||`<p class="empty">No games match ${slateQ?`"${esc(slateQ)}"`:"this filter"}${slateF!=="all"?` at the ${esc(slateF==="lines"?"has lines":tierName(slateF))} level`:""}. Try clearing the search or picking All.</p>`;
}

/* ---------- schedule ---------- */
function renderSchedule(){
  $("tzNote").textContent=tzName?`Times in ${tzName}`:"";
  if(!S){$("schedule").innerHTML=`<p class="empty">The schedule appears after the first line scan of the week.</p>`;return;}
  let html="",day="";
  const games=[...S.games].sort((a,b)=>String(a.start).localeCompare(String(b.start)));
  for(const g of games){
    if(schedF==="plays"&&RANK[tier(g)]<2)continue;
    if(!matchQ(g,schedQ))continue;
    const d=when(g.start,{weekday:"long",month:"short",day:"numeric"});
    if(d!==day){day=d;const n=games.filter(x=>when(x.start,{weekday:"long",month:"short",day:"numeric"})===d).length;html+=`<h3 class="day">${esc(d)}<small>${n} game${n===1?"":"s"}</small></h3>`;}
    const s=cons(g,"spread_home"),t=cons(g,"total"),b=g.best;
    html+=`<a class="srow t-${tier(g)}" href="${gameHref(g.id)}">
      <span class="num sub">${esc(when(g.start,{hour:"numeric",minute:"2-digit"}))}</span>
      <span class="gm">${esc(g.away)} @ ${esc(g.home)}<small>Model ${g.projection?.away??"–"}–${g.projection?.home??"–"}${g.neutral?" · neutral":""} ${wxChip(g)}</small></span>
      <span class="num r">${esc(s==null?"–":`${short(s<=0?g.home:g.away)} ${fmt(s<=0?s:-s)}`)}</span><span class="num r">${fmtT(t)}</span>
      <span class="pkc">${b&&RANK[b.tier]>=1?`${pill(b.tier)}<span>${esc(b.label)}</span>`:`<span class="label">No play</span>`}</span></a>`;
  }
  $("schedule").innerHTML=html||`<p class="empty">${schedQ?`No games match "${esc(schedQ)}".`:"No plays yet this week."}</p>`;
}

/* ---------- matchup ---------- */
function spark(g){
  const h=(g.history||[]).filter(x=>x[1]!=null);
  if(h.length<2)return `<p class="sub" style="margin-top:8px">Movement shows after two or more scans.</p>`;
  const Wd=520,Ht=140,Px=34,vals=h.map(x=>x[1]).concat([g.projection.spread]);
  const mn=Math.min(...vals)-1,mx=Math.max(...vals)+1;
  const x=i=>Px+i*(Wd-Px-10)/(h.length-1),y=v=>10+(v-mn)/(mx-mn)*(Ht-34);
  const pts=h.map((r,i)=>`${x(i)},${y(r[1])}`).join(" ");
  const ticks=[mn+1,(mn+mx)/2,mx-1].map(v=>Math.round(v*2)/2);
  return `<svg class="spark" viewBox="0 0 ${Wd} ${Ht}" role="img" aria-label="${esc(g.home)} spread moved from ${fmt(h[0][1])} to ${fmt(h[h.length-1][1])}; model says ${fmt(g.projection.spread)}">
   ${ticks.map(v=>`<line x1="${Px}" x2="${Wd-10}" y1="${y(v)}" y2="${y(v)}" stroke="var(--border)"/><text x="0" y="${y(v)+4}">${fmt(v)}</text>`).join("")}
   <line x1="${Px}" x2="${Wd-10}" y1="${y(g.projection.spread)}" y2="${y(g.projection.spread)}" stroke="var(--good)" stroke-dasharray="4 4"/>
   <text x="${Wd-12}" y="${y(g.projection.spread)-6}" text-anchor="end" style="fill:var(--good)">model ${fmt(g.projection.spread)}</text>
   <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round"/>
   <circle cx="${x(h.length-1)}" cy="${y(h[h.length-1][1])}" r="4.5" fill="var(--accent)"/>
   <text x="${Px}" y="${Ht-4}">${esc(when(h[0][0]))}</text><text x="${Wd-10}" y="${Ht-4}" text-anchor="end">Now</text></svg>`;
}
function unitBars(A,H){
  if(!A||!H)return `<p class="sub">Grades appear after each team has played a game this season.</p>`;
  return `<div class="units">${UNITS.map(([k,nm])=>{const a=A.grades[k],h=H.grades[k];if(a==null||h==null)return "";return `<div class="unit">
    <span class="num" style="text-align:right;${a>h?"font-weight:600":"color:var(--text-2)"}">${a.toFixed(1)}</span>
    <div class="track l" aria-hidden="true"><i style="width:${a*10}%;background:${gcol(a)}"></i></div><span class="nm">${nm}</span>
    <div class="track r" aria-hidden="true"><i style="width:${h*10}%;background:${gcol(h)}"></i></div>
    <span class="num" style="${h>a?"font-weight:600":"color:var(--text-2)"}">${h.toFixed(1)}</span></div>`}).join("")}</div>`;
}
function clashes(A,H){
  if(!A||!H)return "";
  return `<div class="clash">${[[`${A.team} pass O vs ${H.team} pass D`,A.grades.pass-H.grades.passD],[`${A.team} rush O vs ${H.team} rush D`,A.grades.rush-H.grades.rushD],
    [`${H.team} pass O vs ${A.team} pass D`,H.grades.pass-A.grades.passD],[`${H.team} rush O vs ${A.team} rush D`,H.grades.rush-A.grades.rushD]]
    .map(([k,v])=>`<div><span>${esc(k)}</span><span class="num ${v>.3?"up":v<-.3?"down":""}">${v>0?"+":""}${v.toFixed(1)}</span></div>`).join("")}</div>`;
}
function vcard(title,g,p,extra){
  if(!p)return `<div class="vcard"><span class="label">${title}</span><div class="big muted">No line yet</div></div>`;
  const pr=pickPrice(g,p);
  return `<div class="vcard ${p.tier}"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><span class="label">${title}</span>${pill(p.tier)}</div><div class="big">${esc(p.label)}</div>
    <div class="sub">${extra} Best number: ${BOOK[p.book]||p.book}${pr!=null?` at ${fmtP(pr)}`:""}. ${p.pattern?`${esc(PATTERN[p.pattern])}: ${(p.cover*100).toFixed(1)}% against the closing line since 1999`:`Model edge ${p.edge.toFixed(1)} pts, about a ${(p.cover*100).toFixed(1)}% chance to cover`} (52.4% breaks even).</div>
    ${p.note?`<div class="play-note">${esc(p.note)}</div>`:""}${p.tier==="lock"?`<div class="sub"><b>Before betting:</b> check the wind forecast again near kickoff.</div>`:""}</div>`;
}
function whyPanel(title,p,w){
  if(!p||!w)return "";
  const factors=w.factors||[];
  const mx=Math.max(4,...factors.map(f=>Math.abs(f.points)));
  const bars=factors.map(f=>{const pct=Math.abs(f.points)/mx*50;
    return `<div class="fac"><span title="${esc(f.label)}">${esc(f.label)}</span><div class="fbar" aria-hidden="true"><i style="${f.points>=0?`left:50%`:`right:50%`};width:${pct}%;background:${f.points>=0?"var(--good)":"var(--bad)"}"></i></div><span class="num" style="text-align:right">${f.points>0?"+":""}${f.points.toFixed(1)}</span></div>`}).join("");
  const ck=c=>c.ok===true?`<span class="ck y" role="img" aria-label="Passed">✓</span>`:c.ok===false?`<span class="ck n" role="img" aria-label="Not met">✗</span>`:`<span class="ck q" role="img" aria-label="Check this yourself">?</span>`;
  const news=w.news||[],risks=w.risks||[],evidence=w.evidence||[],reasons=w.reasons||[],checks=w.checks||[];
  return `<section class="panel why" aria-label="Why ${esc(title)}"><div><span class="label">Why ${esc(title)}</span><h3>${esc(p.label)} ${pill(p.tier)}</h3></div>
    ${w.summary?`<p class="lead">${esc(w.summary)}</p>`:""}
    <div class="grid2">
      <div class="col"><span class="label">Where the number comes from</span>${bars||`<p class="sub">No breakdown for this pick.</p>`}${w.factor_note?`<p class="sub">${esc(w.factor_note)}</p>`:""}</div>
      <div class="col"><span class="label">What drives it</span>${reasons.length?`<ul>${reasons.map(r=>`<li>${esc(r)}</li>`).join("")}</ul>`:`<p class="sub">–</p>`}</div>
    </div>
    <div class="grid2">
      <div class="col"><span class="label">Checks</span><div class="checks">${checks.map(c=>`<div>${ck(c)}<span>${esc(c.text)}</span></div>`).join("")||`<p class="sub">–</p>`}</div></div>
      <div class="col"><span class="label">What could go wrong</span>${risks.length?risks.map(r=>`<div class="risk">${esc(r)}</div>`).join(""):`<p class="sub">No red flags the model can see. That doesn't cover injuries or weather.</p>`}
        ${evidence.length?`<span class="label" style="margin-top:6px">How picks like this have done</span><ul>${evidence.map(r=>`<li>${esc(r)}</li>`).join("")}</ul>`:""}</div>
    </div>
    ${news.length?`<div class="col"><span class="label">Latest news (last 4 days)</span><ul class="news">${news.map(h=>`<li>${h.flag?`<span class="badge ${h.flag==="qb"?"b-qb":"b-inj"}">${h.flag==="qb"?"QB":"Injury"}</span>`:""}<a href="${esc(h.link)}" target="_blank" rel="noopener noreferrer">${esc(h.title)}</a> <span class="sub">${esc(h.source)} · ${esc(when(h.published,{weekday:"short",hour:"numeric",minute:"2-digit"}))}</span></li>`).join("")}</ul></div>`:""}
    </section>`;
}
function renderMatchup(){
  if(!S||!S.games.length){$("matchup").innerHTML=`<div class="panel state"><h2>No games yet</h2><p>Games appear after the first line scan of the week. In the meantime, Compare works for any two teams.</p><a class="btn" href="#/compare">Compare teams</a></div>`;return;}
  const g=S.games.find(x=>x.id===cur)||S.games.find(x=>x.best&&x.best.tier!=="pass")||S.games[0];cur=g.id;
  if($("gameSel").value!==g.id)$("gameSel").value=g.id;
  const A=TEAMS[g.away],H=TEAMS[g.home],p=g.projection||{};
  const books=Object.entries(g.lines||{});
  $("matchup").innerHTML=`
  <div class="panel"><div class="mhead">
    <div><div class="label">Away${A?" · "+esc(A.record):""}</div><h2 class="mtitle" tabindex="-1">${esc(full(g.away))}</h2><div class="bar-c" style="background:${color(g.away)}"></div></div>
    <div><div class="score num" aria-label="Model score ${esc(g.away)} ${p.away}, ${esc(g.home)} ${p.home}">${p.away??"–"}–${p.home??"–"}</div><div class="sub">Model score</div><div class="sub">${timeTag(g.start,kick(g.start))}${g.neutral?" · neutral":""}</div>${g.venue?`<div class="sub">${esc(g.venue)}</div>`:""}${g.weather?`<div class="sub">${wxChip(g)} · ${esc(g.weather.short||"")}${g.weather.temp!=null?`, ${g.weather.temp}°F`:""}</div>`:g.roof&&g.roof!=="outdoors"?`<div class="sub">${wxChip(g)}</div>`:""}</div>
    <div><div class="label">Home${H?" · "+esc(H.record):""}</div><h2>${esc(full(g.home))}</h2><div class="bar-c" style="background:${color(g.home)}"></div></div></div></div>
  <div class="verdict">
    ${g.best?`<div class="vcard full ${g.best.tier}"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><span class="label">The pick</span>${pill(g.best.tier)}</div><div class="big">${esc(g.best.label)}</div>
      <div class="sub">${g.best.pattern?esc(PATTERN[g.best.pattern]):`${g.best.edge.toFixed(1)} point model edge`} at the best line, ${BOOK[g.best.book]||g.best.book}${pickPrice(g,g.best)!=null?` (${fmtP(pickPrice(g,g.best))})`:""}.</div></div>`:""}
    ${vcard("Spread",g,g.picks?.spread,`Model ${esc(g.home)} ${fmt(p.spread)}.`)}
    ${vcard("Total",g,g.picks?.total,`Model total ${p.total??"–"}.`)}
  </div>
  ${whyPanel("the spread pick",g.picks?.spread,g.why?.spread)}${whyPanel("the total pick",g.picks?.total,g.why?.total)}
  <div class="grid2">
    <div class="panel"><div style="display:flex;justify-content:space-between;gap:8px;margin-bottom:12px"><span class="label">${esc(g.away)}</span><span class="label">Unit grades</span><span class="label">${esc(g.home)}</span></div>
      ${unitBars(A,H)}${A&&H?`<p class="foot">QBs (most recent starter): ${esc(A.qb?.name??"unknown")} vs ${esc(H.qb?.name??"unknown")}</p>`:""}</div>
    <div class="panel stack" style="align-content:start;gap:10px"><span class="label">Where the game is decided</span>${clashes(A,H)||`<p class="sub">Needs grades for both teams.</p>`}</div>
  </div>
  <div class="grid2">
    <div class="panel"><span class="label">${esc(g.home)} spread movement</span>${spark(g)}</div>
    <div class="panel"><span class="label">Prices by book</span><div class="scroll" style="margin-top:8px"><table>
      <thead><tr><th scope="col">Book</th><th class="n" scope="col">${esc(short(g.home))} spread</th><th class="n" scope="col">Total</th></tr></thead><tbody>
      ${books.map(([b,l])=>`<tr><td>${BOOK[b]||esc(b)}</td><td class="n">${fmt(l.spread_home)}${price(l.spread_home_price)}</td><td class="n">${l.total??"–"}${price(l.over_price)}</td></tr>`).join("")||`<tr><td colspan="3" class="sub">No lines posted yet.</td></tr>`}
      ${g.open?`<tr><td class="sub">Open</td><td class="n sub">${fmt(g.open.spread_home)}</td><td class="n sub">${fmtT(g.open.total)}</td></tr>`:""}
    </tbody></table></div></div>
  </div>`;
}

/* ---------- lines ---------- */
const FEEDTAG={lock:["lock","LOCK"],move:["","Move"],digest:["digest","Email"],hold:["hold","Held"]};
function renderLines(){
  if(!S){$("scanTable").innerHTML=`<tbody><tr><td class="sub">No scans yet. Lines appear after the first scan of the week.</td></tr></tbody>`;$("feed").innerHTML=`<p class="sub">No alerts yet.</p>`;return;}
  const rows=S.games.filter(g=>Object.keys(g.lines||{}).length);
  $("scanTable").innerHTML=`<thead><tr><th scope="col">Game</th><th class="n" scope="col">Open</th><th class="n" scope="col">Now</th><th class="n" scope="col">Move</th><th class="n" scope="col">Model</th><th class="n" scope="col">O/U</th><th scope="col">Signal</th></tr></thead><tbody>`+
    (rows.map(g=>{const s=cons(g,"spread_home"),t=cons(g,"total"),o=g.open||{};
      const mv=o.spread_home==null||s==null?null:s-o.spread_home;
      return `<tr class="click" data-g="${esc(g.id)}"><td><a class="gamelink" href="${gameHref(g.id)}">${esc(g.away)} @ ${esc(g.home)}</a></td><td class="n">${fmt(o.spread_home)}</td><td class="n"><b>${fmt(s)}</b></td>
      <td class="n ${mv>0?"down":mv<0?"up":""}">${!mv?"–":(mv>0?"▲ ":"▼ ")+Math.abs(mv).toFixed(1)}</td><td class="n">${fmt(g.projection?.spread)}</td>
      <td class="n">${fmtT(o.total)} → ${fmtT(t)}</td><td>${pill(tier(g))}</td></tr>`}).join("")||`<tr><td colspan="7" class="sub">No lines posted yet.</td></tr>`)+`</tbody>`;
  if(S.credits_remaining!=null)$("linesFoot").textContent=`Spreads are for the home team, averaged across DraftKings, FanDuel and Bovada. "Open" is the first number we saw this week. Scanned ${when(S.updated,{weekday:"short",hour:"numeric",minute:"2-digit"})}.`;
  const byId=Object.fromEntries(S.games.map(g=>[g.id,g]));
  $("feed").innerHTML=(S.feed||[]).map(a=>{const [cls,lbl]=FEEDTAG[a.kind]||["",a.kind||"Note"];const g=a.game&&byId[a.game];
    const link=a.url?` <a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">${a.kind==="digest"?"View email":"Alert"}</a>`:"";
    return `<div class="alert"><span class="tag ${cls}">${esc(lbl)}</span>
    <div><div>${esc(a.text)}${link}${g?` · <a href="${gameHref(g.id)}">Open game</a>`:""}</div><div class="sub">${timeTag(a.t,`${when(a.t)} · ${rel(a.t)}`)}</div></div></div>`}).join("")||`<p class="sub">No alerts yet. LOCKs, big line moves and emailed pick sheets show up here.</p>`;
}

/* ---------- results ---------- */
const pct=x=>x==null?"–":(x*100).toFixed(1)+"%";
const sgn=x=>x==null?"–":(x>0?"+":"")+x.toFixed(1);
const TIERNAME={lock:"LOCK",strong:"Strong",lean:"Lean",model:"Model lean",all:"All"};
const thead=cols=>`<thead><tr>${cols.map(c=>`<th scope="col" class="${c[1]?"n":""}">${c[0]}</th>`).join("")}</tr></thead>`;
function renderResults(){
  const sm=P?.summary,o=sm?.overall;
  $("rkpis").innerHTML=[["Record",o?`${o.wins}-${o.losses}${o.pushes?"-"+o.pushes:""}`:"0-0"],["Win rate",pct(o?.win_pct)],["Units",o?sgn(o.units):"–"],["Avg CLV (pts)",sgn(o?.avg_clv)],["Waiting on games",sm?.pending??0]]
    .map(([k,v])=>`<div class="kpi"><div class="label">${k}</div><div class="v num">${v}</div></div>`).join("");
  const order=["total:lock","total:strong","total:lean","spread:strong","spread:model","total:model","spread:all","total:all"];
  const bt=sm?.by_tier||{};
  $("tierTable").innerHTML=thead([["Bet"],["W-L-P",1],["Win %",1],["Units",1],["Avg CLV",1],["Beat close",1]])+`<tbody>`+
    (order.filter(k=>bt[k]).map(k=>{const r=bt[k],[b,t]=k.split(":");return `<tr><td>${b==="spread"?"Spread":"Total"} · ${TIERNAME[t]}</td><td class="n">${r.wins}-${r.losses}-${r.pushes}</td><td class="n">${pct(r.win_pct)}</td><td class="n">${sgn(r.units)}</td><td class="n">${sgn(r.avg_clv)}</td><td class="n">${pct(r.beat_close)}</td></tr>`}).join("")
     ||`<tr><td colspan="6" class="sub" style="white-space:normal">No graded picks yet${sm?.pending?`. ${sm.pending} picks are waiting on their games`:""}. Picks are graded after each game ends.</td></tr>`)+`</tbody>`;
  const rows=Object.values(P?.picks||{}).filter(e=>e.result).sort((a,b)=>String(b.start).localeCompare(String(a.start)));
  $("pickTable").innerHTML=thead([["Date"],["Game"],["Pick"],["Tier"],["Final",1],["Result",1],["CLV",1]])+`<tbody>`+
    (rows.map(e=>`<tr><td class="sub">${esc(when(e.start,{month:"short",day:"numeric"}))}</td><td>${esc(e.away)} @ ${esc(e.home)}</td>
      <td>${esc(e.bet==="spread"?`${e.side} ${fmt(e.line)}`:`${e.side} ${e.line}`)}</td><td>${pill(e.tier)}</td>
      <td class="n">${e.final?`${e.final.away}-${e.final.home}`:"–"}</td><td class="n res-${e.result}">${e.result==="win"?"Win":e.result==="loss"?"Loss":"Push"}</td><td class="n">${sgn(e.clv)}</td></tr>`).join("")
     ||`<tr><td colspan="7" class="sub">Nothing graded yet.</td></tr>`)+`</tbody>`;
  const ir=I?.rows||[];
  $("insTable").innerHTML=thead([["Kind of pick"],["W-L-P",1],["Win %",1],["Units",1],["Avg CLV",1]])+`<tbody>`+
    (ir.map(r=>`<tr class="${r.small_sample?"small":""}"><td>${esc(r.group)} · ${esc(r.label)}</td><td class="n">${r.wins}-${r.losses}-${r.pushes}</td><td class="n">${pct(r.win_pct)}</td><td class="n">${sgn(r.units)}</td><td class="n">${sgn(r.avg_clv)}</td></tr>`).join("")
     ||`<tr><td colspan="5" class="sub">Fills in after the first Sunday grading.</td></tr>`)+`</tbody>`;
  $("weekTable").innerHTML=thead([["Week"],["Picks",1],["W-L-P",1],["Units",1],["Avg CLV",1]])+`<tbody>`+
    ((Array.isArray(W)?W:[]).slice().reverse().map(w=>`<tr><td>${esc(w.season)} · Week ${esc(w.week)}</td><td class="n">${w.picks}</td><td class="n">${w.wins}-${w.losses}-${w.pushes}</td><td class="n">${sgn(w.units)}</td><td class="n">${sgn(w.avg_clv)}</td></tr>`).join("")
     ||`<tr><td colspan="5" class="sub">No weeks archived yet.</td></tr>`)+`</tbody>`;
}

/* ---------- grades & compare ---------- */
function renderGrades(){
  if(!G){$("gradeTable").innerHTML=`<tbody><tr><td class="sub">Team grades aren't available right now.</td></tr></tbody>`;return;}
  $("gradesNote").textContent=`${G.season} season through Week ${G.through_week} · ${G.teams.length} teams`;
  const q=$("search").value.trim().toLowerCase(),c=$("conf").value;
  const rows=G.teams.filter(t=>(!c||t.conference===c)&&`${t.team} ${t.name} ${t.abbr}`.toLowerCase().includes(q));
  rows.sort((a,b)=>sortK==="team"?a.team.localeCompare(b.team)*sortDir:((a.grades[sortK]??0)-(b.grades[sortK]??0))*sortDir);
  const cols=[["team","Team"],...UNITS];
  $("gradeTable").innerHTML=`<thead><tr><th scope="col" class="rank">#</th>${cols.map(([k,l])=>`<th scope="col" class="${k==="team"?"sticky-col":"n"}"${k===sortK?` aria-sort="${sortDir<0?"descending":"ascending"}"`:""}><button class="sort" type="button" data-k="${k}">${l}${k===sortK?(sortDir<0?" ▾":" ▴"):""}</button></th>`).join("")}</tr></thead><tbody>`+
    (rows.map((t,i)=>`<tr><td class="rank">${i+1}</td><td class="sticky-col"><button class="teamlink" type="button" data-team="${esc(t.team)}" aria-label="Compare ${esc(t.team)}"><span class="swatch" style="background:${esc(t.color||"var(--text-3)")}"></span>${esc(t.team)} <span class="label">${esc(t.record)}</span></button></td>${UNITS.map(([k])=>`<td class="n">${chip(t.grades[k])}</td>`).join("")}</tr>`).join("")
     ||`<tr><td colspan="${cols.length+1}" class="sub">No teams match "${esc(q)}".</td></tr>`)+`</tbody>`;
}
function renderCompare(){
  const A=TEAMS[$("away").value],H=TEAMS[$("home").value];
  if(!A||!H){$("compare").innerHTML=`<p class="sub">Team grades aren't available right now.</p>`;return;}
  $("compare").innerHTML=`<div class="vs"><div><div class="label">${esc(A.record)} · ${esc(A.conference||"")}</div><h2>${esc(A.name||A.team)}</h2></div><span class="label">at</span>
    <div><div class="label">${esc(H.record)} · ${esc(H.conference||"")}</div><h2>${esc(H.name||H.team)}</h2></div></div>
    ${unitBars(A,H)}<p class="foot">QBs: ${esc(A.qb?.name??"unknown")} vs ${esc(H.qb?.name??"unknown")}</p><div style="margin-top:var(--s4)">${clashes(A,H)}</div>`;
}

/* ---------- theme ---------- */
function curTheme(){const t=document.documentElement.getAttribute("data-theme");return t||(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");}
function syncThemeBtn(){const t=curTheme();$("themeBtn").setAttribute("aria-label",`Switch to ${t==="dark"?"light":"dark"} theme`);$("themeBtn").title=`Switch to ${t==="dark"?"light":"dark"} theme`;}
$("themeBtn").addEventListener("click",()=>{const n=curTheme()==="dark"?"light":"dark";document.documentElement.setAttribute("data-theme",n);
  try{localStorage.setItem("ne-theme",n)}catch(e){}syncThemeBtn();});
try{matchMedia("(prefers-color-scheme: dark)").addEventListener("change",syncThemeBtn)}catch(e){}
syncThemeBtn();

/* ---------- wiring ---------- */
const tabBtns=[...document.querySelectorAll(".tab")];
tabBtns.forEach((b,i)=>{
  b.addEventListener("click",()=>go(b.dataset.tab));
  b.addEventListener("keydown",e=>{let j=null;
    if(e.key==="ArrowRight")j=(i+1)%tabBtns.length;else if(e.key==="ArrowLeft")j=(i-1+tabBtns.length)%tabBtns.length;
    else if(e.key==="Home")j=0;else if(e.key==="End")j=tabBtns.length-1;
    if(j!=null){e.preventDefault();tabBtns[j].focus();go(tabBtns[j].dataset.tab);}});
});
addEventListener("hashchange",route);
$("scanTable").addEventListener("click",e=>{if(e.target.closest("a"))return;const tr=e.target.closest("tr[data-g]");if(tr)location.hash=gameHref(tr.dataset.g);});
$("gameSel").addEventListener("change",()=>{cur=$("gameSel").value;renderMatchup();setHashQuiet(gameHref(cur));});
const chipGroup=(id,set,render)=>$(id).addEventListener("click",e=>{const b=e.target.closest(".chip");if(!b)return;set(b.dataset.f);
  $(id).querySelectorAll(".chip").forEach(c=>c.setAttribute("aria-pressed",c===b));render();});
chipGroup("slateFilters",v=>slateF=v,renderSlate);
chipGroup("schedFilters",v=>schedF=v,renderSchedule);
$("slateQ").addEventListener("input",e=>{slateQ=e.target.value.trim().toLowerCase();renderSlate();});
$("schedQ").addEventListener("input",e=>{schedQ=e.target.value.trim().toLowerCase();renderSchedule();});
$("gradeTable").addEventListener("click",e=>{
  const th=e.target.closest(".sort");if(th){const k=th.dataset.k;if(k===sortK)sortDir*=-1;else{sortK=k;sortDir=k==="team"?1:-1;}renderGrades();
    const nb=$("gradeTable").querySelector(`.sort[data-k="${k}"]`);if(nb)nb.focus();return;}
  const tb=e.target.closest("[data-team]");if(tb){const t=tb.dataset.team;$("away").value=t;
    if($("home").value===t)$("home").value=G.teams.find(x=>x.team!==t).team;renderCompare();go("compare");}
});
["search","conf"].forEach(id=>$(id).addEventListener("input",renderGrades));
["away","home"].forEach(id=>$(id).addEventListener("change",()=>{renderCompare();setHashQuiet(hashFor("compare"));}));

const get=u=>fetch(u,{cache:"no-store"}).then(r=>r.ok?r.json():null).catch(()=>null);
function renderAll(){renderStatus();renderHero();renderSlate();renderSchedule();renderMatchup();renderLines();renderResults();renderGrades();renderCompare();}
function showError(){
  const box=`<div class="panel state" role="alert"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>
    <h2>We couldn't load this week's data</h2><p>Check your connection and try again. If it keeps happening, the data update may be in progress; give it a minute.</p><button class="btn primary" type="button" data-retry>Try again</button></div>`;
  $("hero").removeAttribute("aria-busy");$("hero").innerHTML=box;$("slate").innerHTML="";
  $("status").innerHTML=`<span class="live stale" aria-hidden="true"></span><span>Data unavailable</span>`;
}
document.addEventListener("click",e=>{if(e.target.closest("[data-retry]")){$("hero").innerHTML=`<div class="plays"><div class="skel skel-card"></div><div class="skel skel-card"></div></div>`;load(true);}});
function load(first){
  return Promise.all(["grades","slate","picks","insights","archive/index"].map(n=>get(`data/${n}.json`))).then(([g,s,pk,ins,wk])=>{
    if(!g&&!s){if(first||!loaded)showError();return;}
    const firstData=!loaded;
    G=g;S=s&&Array.isArray(s.games)?s:null;P=pk;I=ins;W=Array.isArray(wk)?wk:(wk?.weeks||wk);TEAMS=g?Object.fromEntries(g.teams.map(t=>[t.team,t])):{};loaded=true;
    const sample=g?.sample||s?.sample;$("banner").hidden=!sample;
    $("banner").textContent="Sample data. Real numbers appear after the update jobs run.";
    if(firstData&&g){
      $("conf").innerHTML=`<option value="">All divisions</option>`+[...new Set(g.teams.map(t=>t.conference).filter(Boolean))].sort().map(c=>`<option>${esc(c)}</option>`).join("");
      const opts=[...g.teams].sort((a,b)=>a.team.localeCompare(b.team)).map(t=>`<option>${esc(t.team)}</option>`).join("");
      $("away").innerHTML=opts;$("home").innerHTML=opts;$("away").value=g.teams[1]?.team;$("home").value=g.teams[0]?.team;
    }
    $("gameSel").innerHTML=(S?.games||[]).map(x=>`<option value="${esc(x.id)}">${esc(x.away)} @ ${esc(x.home)}</option>`).join("");
    if(firstData)route();
    renderAll();
  });
}
route();
load(true);
setInterval(()=>{if(!document.hidden)load(false)},5*60*1000); // pick up new scans without a reload
setInterval(()=>{if(loaded&&!document.hidden)renderStatus()},60*1000);
