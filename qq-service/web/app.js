'use strict';
let state = null;
let changing = false;
const el = id => document.getElementById(id);
const titles = {overview:'运行总览',workbench:'校园通知工作台',access:'访问与群管理',notices:'通知查询',connect:'接入设置'};

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
function view(name){document.querySelectorAll('.view').forEach(s=>s.hidden=s.id!==name);document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.view===name));el('view-title').textContent=titles[name];if(name==='workbench'&&!el('radar-frame').getAttribute('src'))el('radar-frame').src='http://127.0.0.1:8765/';}
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function safeLink(url){try{const p=new URL(url);return ['http:','https:'].includes(p.protocol)?p.href:'#';}catch{return '#';}}
function status(id,text,good){el(id).textContent=text;el(id).classList.toggle('good',good);}
function render(){
  const s=state,c=s.config;
  el('metric-notices').textContent=s.radar.count.toLocaleString();
  el('metric-groups').textContent=c.groups.filter(g=>g.enabled).length;
  el('metric-users').textContent=c.private_users.filter(u=>u.enabled).length;
  el('metric-sent').textContent=s.stats.sent||0;
  const pending=(s.stats.queued||0)+(s.stats.failed||0),uncertain=s.stats.uncertain||0;
  el('metric-pending').textContent=`待发 ${pending} 条${uncertain?` · 结果不确定 ${uncertain} 条（不重发）`:''}`;
  status('qq-status',s.connection.message,s.connection.connected);status('model-status',s.model_ready?'已配置':'未配置 · 关键词查询可用',s.model_ready);status('radar-status',s.radar.ready?'数据库可用':'数据库不可用',s.radar.ready);
  status('weixin-gateway-status',s.services?.weixin_gateway?'端口在线':'未启动',s.services?.weixin_gateway);status('weixin-bridge-status',s.services?.weixin_bridge?'运行中':'未启动',s.services?.weixin_bridge);
  el('last-event').textContent=s.last_event?s.last_event.replace('T',' '):'暂无';
  el('usage-text').textContent=`DeepSeek 累计输入 ${s.usage.input_tokens.toLocaleString()} token / 输出 ${s.usage.output_tokens.toLocaleString()} token；自动推送不调用模型。`;
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
      const remove=node('button','移除','remove');remove.disabled=changing;remove.addEventListener('click',()=>mutate(field,entry.id,null));actions.append(remove);row.append(actions);box.append(row);
    }
  }
}
function settings(){el('bot-qq').value=state.config.bot_qq;el('onebot-url').value=state.config.onebot_url;el('model').value=state.config.model;}
function renderWeixin(w){if(!w)return;if(state)state.weixin=w;const active=['starting','waiting','scanned','verifying'].includes(w.status);el('weixin-status').textContent=w.status==='connected'?'授权完成':w.configured?'已有本地授权':'尚未授权';el('weixin-message').textContent=w.message;el('weixin-start').disabled=active;el('weixin-cancel').hidden=!active;el('weixin-code-form').hidden=!w.code_required;el('weixin-qr').hidden=!w.qr_ready;if(w.qr_ready)el('weixin-qr').src='/api/weixin/qr?t='+Date.now();else el('weixin-qr').removeAttribute('src');}
async function refresh(){state=await api('/api/state');render();}
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
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>view(b.dataset.view)));
el('user-form').addEventListener('submit',async e=>{e.preventDefault();try{await add('private_users',el('user-id').value.trim(),el('user-label').value.trim());e.target.reset();}catch(err){toast(err.message,true);}});
el('group-form').addEventListener('submit',async e=>{e.preventDefault();try{await add('groups',el('group-id').value.trim(),el('group-label').value.trim());e.target.reset();}catch(err){toast(err.message,true);}});
el('refresh-access').addEventListener('click',async()=>{try{await refresh();renderLists();toast('名单已刷新');}catch(e){toast(e.message,true);}});
el('settings-form').addEventListener('submit',async e=>{
  e.preventDefault();if(changing)return;changing=true;const button=e.target.querySelector('button');button.disabled=true;
  try{await api('/api/config',{...state.config,bot_qq:el('bot-qq').value.trim(),onebot_url:el('onebot-url').value.trim(),model:el('model').value,deepseek_key:el('deepseek-key').value.trim()});el('deepseek-key').value='';await refresh();toast('接入设置已保存');}catch(err){toast(err.message,true);}finally{changing=false;button.disabled=false;}
});
document.querySelectorAll('.probe').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{const r=await api('/api/probe',{});await refresh();toast(r.message,!r.connected);}catch(e){toast(e.message,true);}finally{b.disabled=false;}}));
el('export-config').addEventListener('click',async()=>{try{const config=await api('/api/onebot-config');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(config,null,2)],{type:'application/json'}));a.download='onebot-campus-config.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000);toast('配置示例已下载，请只交给本机 QQ 客户端');}catch(e){toast(e.message,true);}});
el('search-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;const box=el('search-results');box.className='empty';box.textContent='正在查询…';try{const result=await api('/api/search?q='+encodeURIComponent(el('search-input').value));box.replaceChildren();box.className=result.items.length?'':'empty';if(!result.items.length)box.textContent='没有匹配结果，试试更短的关键词。';for(const it of result.items){const row=node('article',undefined,'search-result'),link=node('a',it.title);link.href=safeLink(it.url);link.target='_blank';link.rel='noopener noreferrer';row.append(link,node('div',`${it.pub_date||'日期未标明'} · ${it.category_name||'未分类'} · ${it.source_name||''}`,'result-meta'));if(it.digest)row.append(node('p',it.digest.slice(0,180)));box.append(row);}}catch(err){box.textContent=err.message;}finally{button.disabled=false;}});
el('logout').addEventListener('click',async()=>{await api('/api/logout',{});showLogin();});
el('reload-workbench').addEventListener('click',()=>{el('radar-frame').src='http://127.0.0.1:8765/';});
el('weixin-start').addEventListener('click',async()=>{el('weixin-start').disabled=true;try{renderWeixin(await api('/api/weixin/start',{}));toast('微信扫码流程已启动，请本人确认授权');}catch(e){el('weixin-start').disabled=false;toast(e.message,true);}});
el('weixin-cancel').addEventListener('click',async()=>{try{renderWeixin(await api('/api/weixin/cancel',{}));}catch(e){toast(e.message,true);}});
el('weixin-code-form').addEventListener('submit',async e=>{e.preventDefault();try{const w=await api('/api/weixin/code',{code:el('weixin-code').value});el('weixin-code').value='';renderWeixin(w);}catch(err){toast(err.message,true);}});
setInterval(()=>{el('clock').textContent=new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric'});},1000);
setInterval(async()=>{if(!el('shell').hidden&&!changing){try{await refresh();}catch{}}},15000);
setInterval(async()=>{if(state&&['starting','waiting','scanned','verifying'].includes(state.weixin?.status)&&!el('shell').hidden){try{await refresh();}catch{}}},3000);
(async()=>{const fragment=new URLSearchParams(location.hash.slice(1));const token=fragment.get('token');history.replaceState(null,'',location.pathname);try{if(token)await enter(token);else{await refresh();el('login').hidden=true;el('shell').hidden=false;renderLists();settings();}}catch(e){showLogin();if(token)el('login-error').textContent=e.message;}})();
