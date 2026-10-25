'use strict';
(() => {
 const $=s=>document.querySelector(s);let token=location.hash.slice(1)||sessionStorage.getItem('kg.mac.manual')||'';
 if(token){sessionStorage.setItem('kg.mac.manual',token);history.replaceState(null,'',location.pathname);}
 let state=null,frame='',busy=false,typing=Promise.resolve(),stopped=false;
 async function api(path,body){const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+token,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw Error(data.error||'连接暂时不可用');return data;}
 function message(value){$('#message').textContent=value;}
 async function input(value){if(stopped||state?.stage!=='manual_login')return;await api('/input',value);}
 async function status(){try{state=await api('/status');const until=new Date(state.expires_at);$('#status').textContent=(state.stage==='testing'?'原生测试正在运行':'等待本人完成学校登录')+' · 本轮画面截至 '+until.toLocaleTimeString();const locked=state.stage!=='manual_login';for(const b of document.querySelectorAll('button,input'))b.disabled=locked;if(locked)message('人工操作已完成，正在验证双向SSH并运行三领域原生测试。请回到原工作台查看进度与结果。');}catch(error){message(error.message);}}
 async function picture(){if(busy||stopped)return;busy=true;try{const response=await fetch('/screen',{headers:{Authorization:'Bearer '+token}});if(!response.ok)throw Error('画面暂未就绪，请稍候');const next=URL.createObjectURL(await response.blob());$('#screen').src=next;if(frame)URL.revokeObjectURL(frame);frame=next;}catch(error){message(error.message);}finally{busy=false;}}
 $('#screen').onclick=event=>{if(!state)return;const box=$('#screen').getBoundingClientRect(),x=Math.round((event.clientX-box.left)/box.width*state.screen_width),y=Math.round((event.clientY-box.top)/box.height*state.screen_height);$('#screen-area').focus();typing=typing.then(()=>input({action:'click',x,y})).catch(error=>message(error.message));};
 $('#screen-area').onkeydown=event=>{if(!state||state.stage!=='manual_login')return;if(['Meta','Shift','Control','Alt','CapsLock'].includes(event.key))return;event.preventDefault();const modifiers=[];if(event.metaKey||event.ctrlKey)modifiers.push('command down');if(event.altKey)modifiers.push('option down');if(event.shiftKey)modifiers.push('shift down');typing=typing.then(()=>input({action:'key',key:event.key,modifiers})).catch(error=>message(error.message));};
 $('#show-text').onchange=()=>{$('#text').type=$('#show-text').checked?'text':'password';};
 $('#send-text').onclick=async()=>{const text=$('#text').value;if(!text){message('请先输入需要发送的文字。');return;}$('#text').value='';try{await input({action:'text',text});message('已发送到Mac当前选中的输入框。');}catch(error){message(error.message);}};
 for(const button of document.querySelectorAll('[data-key]'))button.onclick=()=>input({action:'key',key:button.dataset.key,modifiers:[]}).catch(error=>message(error.message));
 $('#select-all').onclick=()=>input({action:'key',key:'a',modifiers:['command down']}).catch(error=>message(error.message));
 $('#switch-app').onclick=()=>input({action:'key',key:'Tab',modifiers:['command down']}).catch(error=>message(error.message));
 $('#check').onclick=async()=>{try{const result=await api('/check',{});message(result.campus_ssh_reachable?'校园网SSH已可达，可以点击“登录完成，继续测试”。':'校园网SSH暂未连通。请完成Safari学校认证，并查看aTrust是否已连接。');}catch(error){message(error.message);}};
 $('#continue').onclick=async()=>{try{await api('/continue',{});message('连接检查已通过，正在启动原生测试。');await status();}catch(error){message(error.message);}};
 $('#stop').onclick=async()=>{try{await api('/stop',{});stopped=true;message('本轮已请求结束。可以关闭本页，原工作台保留执行记录。');}catch(error){message(error.message);}};
 if(!token){message('缺少本轮访问凭据，请从现有工作台点击“打开Mac人工操作界面”。');return;}
 status();picture();setInterval(picture,1500);setInterval(status,4000);
})();
