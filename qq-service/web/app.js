'use strict';
let state = null;
let changing = false;
const inbox={folder:'all',category:'',items:[],loaded:false,initialized:false,selected:null,detailSequence:0,returnFocus:null};
const manualSelection=new Set();
let manualBatch=null, manualTargetSignature='';
let searchOffset=0, searchQuery=null, searchBusy=false, filtersLoaded=false;
const el = id => document.getElementById(id);
const titles = {overview:'投递中心',workbench:'校园通知工作台',access:'访问与群管理',notices:'通知收件箱',connect:'接入设置'};

async function api(path, data) {
  const response = await fetch(path, {method: data === undefined ? 'GET':'POST', credentials:'same-origin',headers:data === undefined ? {} : {'Content-Type':'application/json'},body:data === undefined ? undefined : JSON.stringify(data)});
  const value = await response.json();
  if (!response.ok) {
    if(response.status === 401 && path !== '/api/login') showLogin();
    throw new Error(value.error || '请求失败');
  }
  return value;
}
function toast(text, error=false) {const box=el('notice');box.textContent=text;box.classList.toggle('error',error);box.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>box.hidden=true,6500);}
function showLogin(){el('login').hidden=false;el('shell').hidden=true;}
function view(name){
  if(!Object.hasOwn(titles,name))return;
  const workbench=name==='workbench';
  document.body.classList.toggle('inbox-mode',name==='notices');
  if(name!=='notices')closeCompose(false);
  document.body.classList.toggle('workbench-mode',workbench);
  if(!workbench)setWorkbenchFocus(false);
  if(name==='notices'){loadSearchFilters();if(state&&!inbox.loaded)runSearch();}
  for(const section of document.querySelectorAll('.view'))section.hidden=section.id!==name;
  for(const button of document.querySelectorAll('.nav')){
    const active=button.dataset.view===name;
    button.classList.toggle('active',active);
    if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
  }
  el('view-title').textContent=titles[name];
  if(workbench&&!el('radar-frame').getAttribute('src'))el('radar-frame').src='/workbench/';
  if(name==='connect'&&!el('pane-qq').hidden)queueMicrotask(refreshQQConsole);
}

function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function safeLink(url){try{const p=new URL(url);return ['http:','https:'].includes(p.protocol)?p.href:'#';}catch{return '#';}}
function status(id,text,good){el(id).textContent=text;el(id).classList.toggle('good',good);}
function render(){
  const s=state,c=s.config;
  el('services-start').disabled=!!s.services?.starting;
  el('services-start').textContent=s.services?.starting?'正在启动…':'一键启动 / 修复';
  el('services-message').textContent=s.services?.error || (s.services?.starting?'正在补齐服务，微信网关首次启动可能需要几分钟…':s.services?.weixin_gateway&&s.services?.weixin_bridge&&s.connection.connected?(s.services?.weixin_push?.status==='restricted'?'服务进程已运行，但微信发送受限；请查看下方投递状态。':'微信与 QQ 服务已就绪。'):'点击一键启动可补齐服务；QQ 登录失效时仍需本人登录。');
  el('metric-notices').textContent=s.radar.count.toLocaleString();
  el('inbox-health').textContent='本地档案 · '+s.radar.count.toLocaleString()+' 条';
  el('metric-groups').textContent=c.groups.filter(g=>g.enabled).length;
  el('metric-users').textContent=c.private_users.filter(u=>u.enabled).length;
  el('metric-sent').textContent=s.stats.sent||0;
  const pending=(s.stats.queued||0)+(s.stats.failed||0),uncertain=s.stats.uncertain||0;
  el('metric-pending').textContent=`待发 ${pending} 条${uncertain?` · 结果不确定 ${uncertain} 条（不重发）`:''}`;
  status('qq-status',s.connection.message,s.connection.connected);status('model-status',s.model_ready?'已配置':'未配置 · 关键词查询可用',s.model_ready);status('radar-status',s.radar.ready?'数据库可用':'数据库不可用',s.radar.ready);
  status('weixin-gateway-status',s.services?.weixin_gateway?'端口在线':s.services?.starting?'启动中':'未启动',s.services?.weixin_gateway);status('weixin-bridge-status',s.services?.weixin_bridge?'运行中':s.services?.starting?'等待网关 / 启动中':'未启动',s.services?.weixin_bridge);
  el('last-event').textContent=s.last_event?s.last_event.replace('T',' '):'暂无';
  el('usage-text').textContent=`DeepSeek 累计输入 ${s.usage.input_tokens.toLocaleString()} token / 输出 ${s.usage.output_tokens.toLocaleString()} token；自动推送不调用模型。`;
  renderManualTargets();
  const wp=s.services?.weixin_push||{}, limited=wp.status==='restricted';
  status('weixin-push-status',limited?'发送受限':wp.status==='ok'?'最近发送成功':'待确认',wp.status==='ok');
  el('weixin-push-detail').hidden=!limited;
  el('weixin-push-detail').textContent=limited?`${wp.reason}。最近失败：${wp.updated_at||'未知'}；当时待发 ${wp.pending||0} 条。可先给 bot 发消息刷新会话，仍失败需检查平台限制；启动修复不能解除发送限制。`:'';
  if(s.push_preferences?.weixin_push_paused)status('weixin-push-status','自动推送已暂停',false);
  if(s.push_preferences?.qq_push_paused)el('metric-pending').textContent+=' · 自动推送已暂停';
  const crawl=s.crawl_status;
  el('overview-schedule').textContent=`${s.radar.count.toLocaleString()} 条公开通知已归档 · 每 ${s.crawl_minutes} 分钟采集${crawl?.next_run?' · 下次预计 '+crawl.next_run.replace('T',' '):''}`;
  renderCrawlStatus(s.crawl_status);
  renderWeixin(s.weixin);
  const list=el('activity-list');list.replaceChildren();list.className=s.activity.length?'':'empty';
  const kinds={configuration:'设置更新',query:'通知查询',reply_error:'回复异常',query_error:'查询异常',model_error:'模型异常',push_sent:'推送成功',push_failed:'发送失败',push_uncertain:'结果不确定',push_error:'推送异常',busy:'服务繁忙'};
  if(!s.activity.length)list.textContent='配置 QQ 接入后，运行记录将在这里显示。';
  for(const a of s.activity){const row=node('div',undefined,'activity-item');row.append(node('time',a.at.replace('T',' ')),node('span',kinds[a.kind]||a.kind,'kind'),node('span',a.detail));list.append(row);}
}
function renderLists(){
  for(const [field,id] of [['private_users','user-list'],['groups','group-list']]){
    const box=el(id);box.replaceChildren();
    if(!state.config[field].length){box.append(node('div',field==='groups'?'尚未添加测试群':'尚未授权任何私聊 QQ','empty'));continue;}
    for(const entry of state.config[field]){
      const row=node('div',undefined,'list-row'),head=node('div',undefined,'list-head'),info=node('div');info.append(node('strong',entry.label||entry.id),node('small',`${field==='groups'?'群号':'QQ'} ${entry.id}`));head.append(info,node('span',entry.enabled?'已启用':'已停用','chip'));row.append(head);
      const actions=node('div',undefined,'list-actions');
      for(const [property,label] of (field==='groups'?[['enabled','允许群查询'],['push','自动推送']]:[['enabled','允许私聊']])){
        const lab=node('label',undefined,'toggle-label'),input=node('input');input.type='checkbox';input.checked=entry[property];input.disabled=changing;input.addEventListener('change',()=>mutate(field,entry.id,{[property]:input.checked}));lab.append(input,node('span',label));actions.append(lab);
      }
      const remove=node('button','移除','remove');remove.disabled=changing;remove.addEventListener('click',()=>mutate(field,entry.id,null));actions.append(remove);row.append(actions);
      if(field==='groups'){
        const details=node('details'),summary=node('summary','订阅学院 / 部门 / 分类');details.append(summary);
        const sourceLabel=node('label','学院 / 部门（不选表示全部）'),sources=node('select');sources.multiple=true;sources.size=5;sources.setAttribute('aria-label',`群 ${entry.id} 订阅来源`);
        const catLabel=node('label','通知分类（不选表示全部）'),cats=node('select');cats.multiple=true;cats.size=5;cats.setAttribute('aria-label',`群 ${entry.id} 订阅分类`);
        sourceLabel.append(sources);catLabel.append(cats);details.append(sourceLabel,catLabel);
        const help=node('p','同一列表内任一匹配；来源与分类须同时匹配。按住 Ctrl 可多选或取消。仅自动推送使用订阅条件。','muted');details.append(help);
        const save=node('button','保存本群订阅','secondary');save.type='button';save.addEventListener('click',()=>mutate('groups',entry.id,{sources:[...sources.selectedOptions].map(o=>o.value),categories:[...cats.selectedOptions].map(o=>o.value)}));details.append(save);row.append(details);
        fillOptions(cats,state.category_options,entry.categories||[]);
        api('/api/search/filters').then(data=>{const opts={};for(const name of data.sources||[])opts[name]=name;for(const name of entry.sources||[])opts[name]=name;fillOptions(sources,opts,entry.sources||[]);}).catch(()=>{sources.disabled=true;save.disabled=true;help.textContent='来源列表读取失败，请刷新后重试';});
      }
      box.append(row);
    }
  }
}
function settings(){if(!inbox.initialized){inbox.initialized=true;view('notices');}renderPushPreferences();el('crawl-interval').value=state.crawl_minutes;el('crawl-schedule-current').textContent=` 当前每 ${state.crawl_minutes} 分钟一轮`; el('bot-qq').value=state.config.bot_qq;el('onebot-url').value=state.config.onebot_url;el('model').value=state.config.model;}
function renderWeixin(w){if(!w)return;if(state)state.weixin=w;const active=['starting','waiting','scanned','verifying'].includes(w.status);el('weixin-status').textContent=w.status==='connected'?'授权完成':w.configured?'已有本地授权':'尚未授权';el('weixin-message').textContent=w.message;el('weixin-start').disabled=active;el('weixin-cancel').hidden=!active;el('weixin-code-form').hidden=!w.code_required;el('weixin-qr').hidden=!w.qr_ready;if(w.qr_ready)el('weixin-qr').src='/api/weixin/qr?t='+Date.now();else el('weixin-qr').removeAttribute('src');}
async function refresh(){
  const initial=state===null;
  if(initial)el('shell').setAttribute('aria-busy','true');
  try{state=await api('/api/state');render();}
  finally{if(initial)el('shell').removeAttribute('aria-busy');}
}
async function mutate(field,id,changes){
  if(changing)return;
  changing=true;const cfg=structuredClone(state.config);cfg[field]=changes===null?cfg[field].filter(e=>e.id!==id):cfg[field].map(e=>e.id===id?{...e,...changes}:e);renderLists();
  try{await api('/api/config',cfg);await refresh();toast('访问名单已保存');}catch(e){toast(e.message,true);}finally{changing=false;renderLists();}
}
async function add(field,id,label){
  if(changing)return;
  if(state.config[field].some(e=>e.id===id))throw new Error('这个号码已在名单中');
  changing=true;const cfg=structuredClone(state.config);cfg[field].push({id,label,enabled:true,...(field==='groups'?{push:false}:{})});
  try{await api('/api/config',cfg);await refresh();renderLists();toast(field==='groups'?'测试群已添加；可打开自动推送':'私聊 QQ 已授权');}finally{changing=false;}
}
async function enter(token){await api('/api/login',{token});el('admin-token').value='';el('login').hidden=true;el('shell').hidden=false;await refresh();renderLists();settings();}
el('login-form').addEventListener('submit',async e=>{e.preventDefault();try{await enter(el('admin-token').value);}catch(err){el('login-error').textContent=err.message;}});
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{
 if(b.classList.contains('nav')){
  const collapsed=document.body.classList.contains('sidebar-collapsed');
  if(b.classList.contains('active'))setSidebarCollapsed(!collapsed);
 }
 view(b.dataset.view);
}));
el('user-form').addEventListener('submit',async e=>{e.preventDefault();try{await add('private_users',el('user-id').value.trim(),el('user-label').value.trim());e.target.reset();}catch(err){toast(err.message,true);}});
el('group-form').addEventListener('submit',async e=>{e.preventDefault();try{await add('groups',el('group-id').value.trim(),el('group-label').value.trim());e.target.reset();}catch(err){toast(err.message,true);}});
el('refresh-access').addEventListener('click',async()=>{try{await refresh();renderLists();toast('名单已刷新');}catch(e){toast(e.message,true);}});
el('settings-form').addEventListener('submit',async e=>{
  e.preventDefault();if(changing)return;changing=true;const button=e.target.querySelector('button');button.disabled=true;
  try{await api('/api/config',{...state.config,bot_qq:el('bot-qq').value.trim(),onebot_url:el('onebot-url').value.trim(),model:el('model').value,deepseek_key:el('deepseek-key').value.trim()});el('deepseek-key').value='';await refresh();toast('接入设置已保存');}catch(err){toast(err.message,true);}finally{changing=false;button.disabled=false;}
});
document.querySelectorAll('.probe').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{const r=await api('/api/probe',{});await refresh();toast(r.message,!r.connected);}catch(e){toast(e.message,true);}finally{b.disabled=false;}}));
el('export-config').addEventListener('click',async()=>{try{const config=await api('/api/onebot-config');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(config,null,2)],{type:'application/json'}));a.download='onebot-campus-config.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000);toast('配置示例已下载，请只交给本机 QQ 客户端');}catch(e){toast(e.message,true);}});
async function runSearch(offset=0){
 if(searchBusy)return;
 if(offset===0){try{searchQuery={q:el('search-input').value,source:el('search-source').value,start:readChineseDate('search-start'),end:readChineseDate('search-end')};}catch(error){toast(error.message,true);return;}}
 searchBusy=true;el('search-form').querySelector('button').disabled=true;el('search-results').setAttribute('aria-busy','true');
 const box=el('search-results');box.className='inbox-list';box.textContent='正在读取通知…';
 try{
  const result=await api('/api/inbox?'+new URLSearchParams({...searchQuery,folder:inbox.folder,category:inbox.category,offset}));
  inbox.items=result.items;inbox.loaded=true;searchOffset=offset;
  renderInboxList();
  for(const name of ['all','unread','starred'])el('folder-'+name+'-count').textContent=result.counts[name].toLocaleString();
  el('inbox-result-count').textContent=result.total.toLocaleString()+' 条';
  renderInboxCategories(result.categories);
  el('search-prev').disabled=offset===0;el('search-next').disabled=!result.has_more;el('search-page').textContent=`${offset/20+1} / ${Math.max(1,Math.ceil(result.total/20))}`;
 }catch(error){box.replaceChildren(node('p',error.message,'empty'));el('search-prev').disabled=true;el('search-next').disabled=true;}
 finally{searchBusy=false;el('search-results').removeAttribute('aria-busy');el('search-form').querySelector('button').disabled=false;}
}
function renderInboxList(){
 const box=el('search-results');box.replaceChildren();
 if(!inbox.items.length){box.append(node('div','这里暂时没有通知，试试其他筛选条件。','empty'));return;}
 for(const item of inbox.items){
  const row=node('article',undefined,'inbox-item');row.classList.toggle('unread',!item.read);row.classList.toggle('selected',inbox.selected?.url===item.url);
  const check=node('input');check.type='checkbox';check.value=item.url;check.checked=manualSelection.has(item.url);check.setAttribute('aria-label','选择通知：'+item.title);
  check.addEventListener('change',()=>{if(check.checked)manualSelection.add(item.url);else manualSelection.delete(item.url);invalidateManual();});
  const open=node('button',undefined,'notice-open');open.type='button';open.append(node('span',item.source_name||'公开通知','notice-source'),node('strong',item.title),node('span',item.digest||'点击阅读通知正文','notice-excerpt'));
  open.setAttribute('aria-label','阅读通知：'+item.title);open.addEventListener('click',()=>openNotice(item.url));
  const date=node('time',(item.pub_date||item.first_seen||'').slice(0,10),'notice-date');
  const star=node('button',item.starred?'★':'☆','notice-star');star.type='button';star.setAttribute('aria-label',(item.starred?'取消收藏：':'收藏通知：')+item.title);star.setAttribute('aria-pressed',String(item.starred));star.addEventListener('click',async()=>{star.disabled=true;try{await setInboxFlag(item.url,{starred:!item.starred});}catch(error){toast(error.message,true);}finally{star.disabled=false;}});
  const category=node('span',item.category_name||'其他信息','notice-category');category.dataset.category=item.category||'other';
  row.append(check,open,date,star,category);box.append(row);
 }
}
function renderInboxCategories(categories){
 const box=el('inbox-categories');box.replaceChildren();
 fillOptions(el('inbox-category-mobile'),{'':'全部主题',...Object.fromEntries(categories.map(item=>[item.id,item.name]))},[inbox.category]);
 const all=node('button','全部主题','category-filter');all.type='button';all.classList.toggle('active',!inbox.category);all.addEventListener('click',()=>setInboxCategory(''));box.append(all);
 for(const category of categories){const button=node('button',undefined,'category-filter');button.type='button';button.dataset.category=category.id;button.classList.toggle('active',inbox.category===category.id);button.append(node('span',category.name),node('b',String(category.count)));button.addEventListener('click',()=>setInboxCategory(category.id));box.append(button);}
}
function setInboxCategory(category){if(searchBusy)return;inbox.category=category;updateInboxCaption();runSearch();}
function updateInboxCaption(){el('inbox-folder-mobile').value=inbox.folder;const label={all:'全部通知',unread:'未读通知',starred:'我的收藏'}[inbox.folder];el('inbox-folder-title').textContent=label;for(const button of document.querySelectorAll('[data-folder]')){const active=button.dataset.folder===inbox.folder;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));}}
async function openNotice(url){
 const sequence=++inbox.detailSequence;inbox.selected=null;for(const id of ['reader-star','reader-unread','reader-pick'])el(id).hidden=true;document.body.classList.add('reader-open');el('reader-content').replaceChildren(node('div','正在加载正文…','reader-loading'));
 try{
  const item=await api('/api/inbox/detail?'+new URLSearchParams({url}));if(sequence!==inbox.detailSequence)return;
  inbox.selected=item;renderReader();renderInboxList();
  if(!item.read)await setInboxFlag(url,{read:true});
 }catch(error){if(sequence===inbox.detailSequence)el('reader-content').replaceChildren(node('div',error.message,'reader-loading'));}
}
function renderReader(){
 const item=inbox.selected;if(!item)return;
 const box=el('reader-content');box.replaceChildren();
 const meta=node('div',undefined,'reader-meta');meta.append(node('span',item.category_name||'公开通知','reader-category'),node('time',item.pub_date||'日期未标明'));
 box.append(meta,node('h2',item.title,'reader-title'));
 const source=node('div',undefined,'reader-source');source.append(node('span',item.source_name||'学校公开网站'));
 const link=node('a','查看学校原文 ↗');link.href=safeLink(item.url);link.target='_blank';link.rel='noopener noreferrer';source.append(link);box.append(source);
 if(item.deadline)box.append(node('p','截止日期：'+item.deadline,'reader-deadline'));
 const body=node('div',item.body||item.digest||'本地库暂未收录正文，请打开学校原文查看。','reader-body');box.append(body);
 if(item.files){const files=node('section',undefined,'reader-attachments');files.append(node('h3','附件信息'),node('p',item.files),node('small','附件内容请在学校原文中查看，部分附件需要本人登录或验证码。'));box.append(files);}
 const note=node('p','内容来自学校公开通知。以原文最新说明为准。','reader-footnote');box.append(note);
 for(const id of ['reader-star','reader-unread','reader-pick'])el(id).hidden=false;
 el('reader-star').textContent=item.starred?'已收藏':'收藏';el('reader-star').setAttribute('aria-pressed',String(item.starred));
 el('reader-unread').textContent=item.read?'标为未读':'标为已读';el('reader-position').textContent='通知正文';
 el('reader-pick').textContent=manualSelection.has(item.url)?'已加入推送清单':'加入推送清单';
}
async function setInboxFlag(url,change){
 const result=await api('/api/inbox/flags',{url,...change});
 const item=inbox.items.find(item=>item.url===url);const was=item?{read:item.read,starred:item.starred}:inbox.selected?.url===url?{read:inbox.selected.read,starred:inbox.selected.starred}:null;
 if(item)Object.assign(item,result);
 if(inbox.selected?.url===url){Object.assign(inbox.selected,result);renderReader();}
 if(was){for(const [field,folder,inverse] of [['read','unread',true],['starred','starred',false]]){if(was[field]!==result[field]){const element=el('folder-'+folder+'-count');const value=Number(element.textContent.replaceAll(',',''));if(Number.isFinite(value))element.textContent=Math.max(0,value+(result[field]?(inverse?-1:1):(inverse?1:-1))).toLocaleString();}}}
 if((inbox.folder==='starred'&&!result.starred)||(inbox.folder==='unread'&&result.read)){inbox.items=inbox.items.filter(item=>item.url!==url);}
 renderInboxList();
}
el('search-form').addEventListener('submit',e=>{e.preventDefault();runSearch();});
el('search-prev').addEventListener('click',()=>runSearch(Math.max(0,searchOffset-20)));
el('search-next').addEventListener('click',()=>runSearch(searchOffset+20));
el('search-reset').addEventListener('click',()=>{for(const id of ['search-input','search-source','search-start','search-end'])el(id).value='';inbox.category='';runSearch();});
async function loadSearchFilters(){if(filtersLoaded)return;try{const r=await api('/api/search/filters');for(const source of r.sources){const o=node('option',source);o.value=source;el('search-source').append(o);}filtersLoaded=true;}catch(e){toast(e.message,true);}}
el('logout').addEventListener('click',async()=>{await api('/api/logout',{});showLogin();});
el('reload-workbench').addEventListener('click',()=>{el('radar-frame').src='/workbench/';});
el('weixin-start').addEventListener('click',async()=>{el('weixin-start').disabled=true;try{renderWeixin(await api('/api/weixin/start',{}));toast('微信扫码流程已启动，请本人确认授权');}catch(e){el('weixin-start').disabled=false;toast(e.message,true);}});
el('weixin-cancel').addEventListener('click',async()=>{try{renderWeixin(await api('/api/weixin/cancel',{}));}catch(e){toast(e.message,true);}});
el('weixin-code-form').addEventListener('submit',async e=>{e.preventDefault();try{const w=await api('/api/weixin/code',{code:el('weixin-code').value});el('weixin-code').value='';renderWeixin(w);}catch(err){toast(err.message,true);}});
setInterval(()=>{el('clock').textContent=new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric'});},1000);
setInterval(async()=>{if(!el('shell').hidden&&!changing){try{await refresh();}catch{}}},15000);
setInterval(async()=>{if(state&&['starting','waiting','scanned','verifying'].includes(state.weixin?.status)&&!el('shell').hidden){try{await refresh();}catch{}}},3000);
(async()=>{const fragment=new URLSearchParams(location.hash.slice(1));const token=fragment.get('token');history.replaceState(null,'',location.pathname);try{if(token)await enter(token);else{await refresh();el('login').hidden=true;el('shell').hidden=false;renderLists();settings();}}catch(e){showLogin();if(token)el('login-error').textContent=e.message;}})();

el('services-start').addEventListener('click',async()=>{el('services-start').disabled=true;try{const r=await api('/api/services/start',{});await refresh();toast(r.message);}catch(e){toast(e.message,true);}finally{el('services-start').disabled=!!state?.services?.starting;}});
setInterval(async()=>{if(state?.services?.starting&&!el('shell').hidden){try{await refresh();}catch{}}},3000);

function invalidateManual(){updateInboxSelection();manualBatch=null;el('manual-cancel').hidden=true;el('manual-send').hidden=true;el('manual-items').replaceChildren();el('manual-summary').textContent='选择已更新，请重新预览后发送。';updateComposeSteps();}
function renderManualTargets(){
  const c=state.config, sig=JSON.stringify([c.groups,c.private_users]);
  if(sig===manualTargetSignature)return;manualTargetSignature=sig;
  const box=el('manual-targets');box.replaceChildren();invalidateManual();
  for(const [field,kind,title] of [['groups','group','接收群'],['private_users','private','私人 QQ']]){
    const col=node('div');col.append(node('h3',title));
    const rows=c[field].filter(x=>x.enabled);
    if(!rows.length)col.append(node('p','暂无已启用对象，请先在访问与群管理添加。','muted'));
    for(const t of rows){const label=node('label'),pick=node('input');pick.type='checkbox';pick.dataset.kind=kind;pick.value=t.id;pick.addEventListener('change',invalidateManual);label.append(pick,document.createTextNode(' '+(t.name||t.label||t.id)+(t.name||t.label?' · '+t.id:'')));col.append(label);}
    box.append(col);
  }
}
const manualLabels={wait_resend:'已发送过，等待你确认是否重发',prepared:'待确认',queued:'等待发送',sending:'发送中',sent:'发送成功',failed:'发送失败',uncertain:'结果不确定，不重发',skipped:'已发送、待发送、结果不确定或权限变化，已跳过',cancelled:'任务中断，请重新预览'};
function renderManualBatch(result){
  manualBatch=result;updateComposeSteps();el('manual-details').querySelector('summary').textContent=`展开 / 收起推送明细（${result.items.length} 条）`;const box=el('manual-items');box.replaceChildren();
  for(const item of result.items){const row=node('article',undefined,'search-result');row.append(node('strong',(item.target_kind==='group'?'群 ':'私人 QQ ')+item.target_id+' · '+(manualLabels[item.status]||item.status)),node('p',item.message));box.append(row);}
  const duplicates=result.items.filter(x=>x.status==='wait_resend').length;
  const ready=result.items.filter(x=>['prepared','wait_resend'].includes(x.status)).length;
  el('manual-send').textContent=duplicates?'确认重新发送':'确认发送';
  el('manual-cancel').hidden=!ready;
  updateInboxSelection();
  el('manual-send').hidden=!ready;el('manual-send').disabled=false;
  el('manual-summary').textContent=result.active?'正在发送，请勿关闭服务。结果不确定的消息不会自动重发。':duplicates?`这些信息已经发送过，是否重新发送？其中 ${duplicates} 条为重复消息，本次共 ${ready} 条；请核对明细后确认，或取消。`:ready?`将发送 ${ready} 条消息，请核对接收对象和内容后确认。`:`任务状态：成功 ${result.items.filter(x=>x.status==='sent').length}，失败 ${result.items.filter(x=>x.status==='failed').length}，结果不确定 ${result.items.filter(x=>x.status==='uncertain').length}，跳过 ${result.items.filter(x=>x.status==='skipped').length}。`;
}
el('manual-clear').addEventListener('click',()=>{manualSelection.clear();el('search-results').querySelectorAll('input[type=checkbox]').forEach(x=>x.checked=false);el('manual-count').textContent='已选 0 条通知';invalidateManual();});
el('manual-preview').addEventListener('click',async()=>{const b=el('manual-preview');b.disabled=true;try{const targets=[...el('manual-targets').querySelectorAll('input:checked')].map(x=>({kind:x.dataset.kind,id:x.value}));renderManualBatch(await api('/api/manual/preview',{urls:[...manualSelection],targets}));}catch(e){toast(e.message,true);}finally{b.disabled=false;}});
el('manual-send').addEventListener('click',async()=>{if(!manualBatch)return;el('manual-send').disabled=true;try{renderManualBatch(await api('/api/manual/send',{batch:manualBatch.batch,confirm_resend:manualBatch.items.some(x=>x.status==='wait_resend')}));}catch(e){toast(e.message,true);el('manual-send').disabled=false;}});
setInterval(async()=>{if(manualBatch?.active&&!el('shell').hidden){const batch=manualBatch.batch;try{const result=await api('/api/manual/status?batch='+encodeURIComponent(batch));if(manualBatch?.batch===batch)renderManualBatch(result);}catch(e){toast(e.message,true);}}},2000);

el('manual-toggle').addEventListener('click',()=>{const closed=!el('manual-body').hidden;el('manual-body').hidden=closed;el('manual-toggle').textContent=closed?'展开设置':'收起设置';el('manual-toggle').setAttribute('aria-expanded',String(!closed));});
el('manual-panel').append(el('manual-panel').querySelector('.manual-actions'));
el('manual-details').open=false;

el('search-toggle').addEventListener('click',()=>{const open=!el('inbox-advanced').open;el('inbox-advanced').open=open;el('search-toggle').textContent=open?'收起筛选':'展开筛选';el('search-toggle').setAttribute('aria-expanded',String(open));});

function selectSearchPage(invert=false,clear=false){
  const picks=[...el('search-results').querySelectorAll('input[type=checkbox]')];
  if(!picks.length){toast('请先查询通知');return;}
  for(const pick of picks){pick.checked=clear?false:invert?!pick.checked:true;if(pick.checked)manualSelection.add(pick.value);else manualSelection.delete(pick.value);}
  el('manual-count').textContent=`已选 ${manualSelection.size} 条通知`;
  invalidateManual();
  if(manualSelection.size>50)toast(`已选 ${manualSelection.size} 条，每批最多推送50条，请取消部分勾选后预览。`);
}
el('search-select-all').addEventListener('click',()=>selectSearchPage());
el('search-invert').addEventListener('click',()=>selectSearchPage(true));



el('search-deselect-all').addEventListener('click',()=>selectSearchPage(false,true));

function setWorkbenchFocus(on){document.body.classList.toggle('workbench-focus',on);el('workbench-focus').textContent=on?'退出专注':'专注阅读';el('workbench-focus').setAttribute('aria-pressed',String(on));}
el('workbench-focus').addEventListener('click',()=>setWorkbenchFocus(!document.body.classList.contains('workbench-focus')));
document.addEventListener('keydown',e=>{if(e.key==='Escape')setWorkbenchFocus(false);});

function readChineseDate(id){
 const text=el(id).value.trim();if(!text)return '';
 const match=text.match(/^(\d{4})[年/.-]\s*(\d{1,2})[月/.-]\s*(\d{1,2})日?$/);
 if(!match)throw new Error('请填写日期，例如2026年10月15日，或点击日历选择');
 const y=Number(match[1]),m=Number(match[2]),d=Number(match[3]),date=new Date(y,m-1,d);
 if(y<1000||date.getFullYear()!==y||date.getMonth()!==m-1||date.getDate()!==d)throw new Error('日期无效，请重新选择');
 return `${match[1]}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
}
for(const id of ['search-start','search-end']){
 const field=el(id),picker=el(id+'-picker');
 picker.addEventListener('change',()=>{if(picker.value){const [y,m,d]=picker.value.split('-');field.value=`${y}年${m}月${d}日`;}else field.value='';});
 field.addEventListener('blur',()=>{try{const iso=readChineseDate(id);picker.value=iso;if(iso){const [y,m,d]=iso.split('-');field.value=`${y}年${m}月${d}日`;}}catch{}});
}
el('search-reset').addEventListener('click',()=>{el('search-start-picker').value='';el('search-end-picker').value='';});

function setSidebarCollapsed(collapsed){
 document.body.classList.toggle('sidebar-collapsed',collapsed);
 document.body.classList.remove('workbench-wide-nav');
 try{localStorage.setItem('campus-sidebar-collapsed',String(collapsed));}catch{}
}
try{setSidebarCollapsed(localStorage.getItem('campus-sidebar-collapsed')==='true');}catch{setSidebarCollapsed(false);}

el('crawl-schedule-form').addEventListener('submit',async e=>{e.preventDefault();const value=Number(el('crawl-interval').value);if(!Number.isInteger(value)||value<10||value>180)return toast('请输入 10–180 分钟的整数',true);try{const result=await api('/api/crawl/schedule',{interval_minutes:value});state.crawl_minutes=result.interval_minutes;el('crawl-schedule-current').textContent=` 当前每 ${result.interval_minutes} 分钟一轮`;await refresh();toast('抓取间隔已保存，按新间隔调度');}catch(err){toast(err.message,true);}});

function fillOptions(select,options,selected){select.replaceChildren();for(const [value,label] of Object.entries(options||{})){const option=node('option',label);option.value=value;option.selected=selected.includes(value);select.append(option);}}
function renderPushPreferences(){const p=state.push_preferences||{};el('wx-push-paused').checked=!!p.weixin_push_paused;el('qq-push-paused').checked=!!p.qq_push_paused;el('push-exclude-keywords').value=(p.exclude_keywords||[]).join('\n');el('push-max-age').value=p.max_age_days||30;fillOptions(el('push-categories'),state.category_options,p.categories||[]);fillOptions(el('push-exclude-categories'),state.category_options,p.exclude_categories||[]);}
function renderCrawlStatus(c){if(!c)return;el('crawl-state-text').textContent=c.available?`${c.crawling?'正在抓取':'等待下轮'} · 最近抓取：${c.last_run||'暂无'} · 下次预计：${c.next_run?.replace('T',' ')||'等待调度信息'}（以服务运行及当前抓取完成情况为准）`:'通知工作台未连接，暂时无法读取抓取状态';const list=el('crawl-sites');list.replaceChildren();for(const site of c.sites||[])list.append(node('p',`${site.name}：${site.status==='ok'?'成功':site.status} · ${site.count||0} 条`));for(const name of c.unreachable||[])list.append(node('p',`${name}：未接通 / 无可用公开入口`));}
el('push-preferences-form').addEventListener('submit',async e=>{e.preventDefault();try{const value={exclude_keywords:el('push-exclude-keywords').value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean),categories:[...el('push-categories').selectedOptions].map(o=>o.value),exclude_categories:[...el('push-exclude-categories').selectedOptions].map(o=>o.value),max_age_days:Number(el('push-max-age').value),weixin_push_paused:el('wx-push-paused').checked,qq_push_paused:el('qq-push-paused').checked};await api('/api/push/preferences',value);await refresh();toast('推送规则已保存；暂停不影响抓取与查询');}catch(err){toast(err.message,true);}});

el('manual-cancel').addEventListener('click',async()=>{if(!manualBatch)return;try{renderManualBatch(await api('/api/manual/cancel',{batch:manualBatch.batch}));}catch(e){toast(e.message,true);}});

// Settings panels are presentation-only: switching never saves or clears form values.
function showSettingPane(name,focus=false){
 const tabs=[...document.querySelectorAll('[data-setting-tab]')];
 if(!tabs.some(button=>button.dataset.settingTab===name))return;
 for(const button of tabs){const active=button.dataset.settingTab===name;button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;if(active&&focus)button.focus();}
 for(const panel of document.querySelectorAll('.settings-pane'))panel.hidden=panel.id!=='pane-'+name;
 try{sessionStorage.setItem('campus-setting-pane',name);}catch{}
 if(name==='qq')queueMicrotask(refreshQQConsole);
}
for(const button of document.querySelectorAll('[data-setting-tab]')){
 button.addEventListener('click',()=>showSettingPane(button.dataset.settingTab));
 button.addEventListener('keydown',event=>{
  const tabs=[...document.querySelectorAll('[data-setting-tab]')];let index=tabs.indexOf(button);
  if(event.key==='ArrowRight')index=(index+1)%tabs.length;
  else if(event.key==='ArrowLeft')index=(index+tabs.length-1)%tabs.length;
  else if(event.key==='Home')index=0;
  else if(event.key==='End')index=tabs.length-1;
  else return;
  event.preventDefault();showSettingPane(tabs[index].dataset.settingTab,true);
 });
}
try{showSettingPane(sessionStorage.getItem('campus-setting-pane')||'automation');}catch{}

function updateComposeSteps(){
 const step=manualBatch?2:manualSelection.size?1:0;
 document.querySelectorAll('.compose-steps li').forEach((item,index)=>{
  item.classList.toggle('current',index===step);
  item.classList.toggle('complete',index<step);
  if(index===step)item.setAttribute('aria-current','step');else item.removeAttribute('aria-current');
 });
}

function updateInboxSelection(){
 const count=manualSelection.size;el('manual-count').textContent=`已选 ${count} 条通知`;el('inbox-selection-count').textContent=count?`已选 ${count} 条，跨页选择保留`:'勾选通知后可批量推送';el('compose-count').textContent=String(count);if(inbox.selected)renderReader();
}
function openCompose(){inbox.returnFocus=document.activeElement;el('compose-drawer').hidden=false;el('compose-backdrop').hidden=false;document.body.classList.add('compose-open');el('close-compose').focus();}
function closeCompose(restore=true){if(!el('compose-drawer'))return;const wasOpen=!el('compose-drawer').hidden;el('compose-drawer').hidden=true;el('compose-backdrop').hidden=true;document.body.classList.remove('compose-open');if(wasOpen&&restore&&inbox.returnFocus?.isConnected)inbox.returnFocus.focus();}
el('open-compose').addEventListener('click',openCompose);el('close-compose').addEventListener('click',()=>closeCompose());el('compose-backdrop').addEventListener('click',()=>closeCompose());
for(const button of document.querySelectorAll('[data-folder]'))button.addEventListener('click',()=>{if(searchBusy)return;inbox.folder=button.dataset.folder;updateInboxCaption();runSearch();});
el('reader-star').addEventListener('click',async()=>{if(!inbox.selected)return;try{await setInboxFlag(inbox.selected.url,{starred:!inbox.selected.starred});}catch(error){toast(error.message,true);}});
el('reader-unread').addEventListener('click',async()=>{if(!inbox.selected)return;try{await setInboxFlag(inbox.selected.url,{read:!inbox.selected.read});}catch(error){toast(error.message,true);}});
el('reader-pick').addEventListener('click',()=>{if(!inbox.selected)return;manualSelection.add(inbox.selected.url);invalidateManual();renderInboxList();});
el('reader-back').addEventListener('click',()=>document.body.classList.remove('reader-open'));
document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeCompose();document.body.classList.remove('reader-open');}if(event.key==='Tab'&&!el('compose-drawer').hidden){const focusable=[...el('compose-drawer').querySelectorAll('button,input,select,textarea,summary,a[href]')].filter(node=>!node.disabled&&node.getClientRects().length);const first=focusable[0],last=focusable.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}});

el('inbox-folder-mobile').addEventListener('change',event=>{inbox.folder=event.target.value;updateInboxCaption();runSearch();});
el('inbox-category-mobile').addEventListener('change',event=>setInboxCategory(event.target.value));

let qqConsoleBusy=false,qqQrRevision='',qqLoggedIn=false;
function showQQCode(value){
 el('qq-login-box').hidden=!value.qr_ready;
 if(!value.qr_ready){qqQrRevision='';el('qq-login-image').removeAttribute('src');return;}
 if(qqQrRevision!==value.qr_revision){qqQrRevision=value.qr_revision;el('qq-login-image').src='/api/qq-console/qr?t='+encodeURIComponent(qqQrRevision);}
}
async function refreshQQConsole(){
 if(qqConsoleBusy||!state)return;qqConsoleBusy=true;el('qq-console-refresh').disabled=true;
 try{
  const value=await api('/api/qq-console/state');
  el('qq-console-badge').textContent=value.logged_in?'已登录':value.available?'等待登录':'未连接';
  el('qq-console-message').textContent=value.message;
  qqLoggedIn=!!value.logged_in;el('qq-login-qr').hidden=qqLoggedIn;
  const rows=[['QQ 登录',value.logged_in?'已登录':value.available?'等待扫码 / 手机确认':'客户端未就绪',value.logged_in],['消息发送接口',value.connection?.connected?'已连接 · QQ '+value.connection.qq:value.logged_in?(value.connection?.message||'未连接'):'登录后检查',!!value.connection?.connected],['发送通道配置',value.outgoing_configured?'匹配本项目':'尚未就绪或不匹配',!!value.outgoing_configured],['消息回传配置',value.incoming_configured?'匹配本项目':'尚未就绪或不匹配',!!value.incoming_configured],['本次运行最近收信',state.last_event?.replace('T',' ')||'暂无记录',!!state.last_event]];
  const box=el('qq-diagnostics');box.replaceChildren();for(const [label,text,good] of rows)box.append(node('dt',label),node('dd',text,good?'ok':'warning'));
  const queued=state.stats.queued||0;el('qq-queue-note').textContent=`待发 ${queued} 条 · ${state.push_preferences?.qq_push_paused?'QQ 自动推送已暂停，可在采集与推送中恢复。':'登录成功后会按现有规则自动发送。'}结果不确定的消息不会自动重发。`;
  if(value.available&&!value.logged_in){
   if(value.qr_ready)showQQCode(value);
   else{showQQCode({qr_ready:false});const code=await api('/api/qq-console/qr',{});showQQCode(code);el('qq-console-message').textContent=code.message;}
  }else showQQCode({qr_ready:false});
 }catch(error){el('qq-console-message').textContent=error.message;}
 finally{qqConsoleBusy=false;el('qq-console-refresh').disabled=false;}
}
el('qq-console-refresh').addEventListener('click',refreshQQConsole);
el('qq-login-qr').addEventListener('click',async()=>{if(qqConsoleBusy)return;qqConsoleBusy=true;el('qq-login-qr').disabled=true;try{const value=await api('/api/qq-console/qr',{refresh:true});el('qq-console-message').textContent=value.message;showQQCode(value);}catch(error){showQQCode({qr_ready:false});toast(error.message,true);}finally{qqConsoleBusy=false;el('qq-login-qr').disabled=qqLoggedIn;}});
el('qq-console-start').addEventListener('click',async()=>{el('qq-console-start').disabled=true;try{await api('/api/services/start',{});toast('已请求启动 / 修复，请稍后刷新状态。');await refreshQQConsole();}catch(error){toast(error.message,true);}finally{el('qq-console-start').disabled=false;}});
setInterval(()=>{if(!el('connect').hidden&&!el('pane-qq').hidden&&!el('shell').hidden&&!document.hidden)refreshQQConsole();},10000);
