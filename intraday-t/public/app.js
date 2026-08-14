fetch('/api/status').then(r=>r.json()).then(x=>{if(!x.demo)document.querySelector('#demo').textContent='本地模式'});

document.querySelector('#settings').addEventListener('submit',async e=>{e.preventDefault();let value=Object.fromEntries(new FormData(e.target));await fetch('/api/config',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(value)});alert('已保存到本机；重启服务后生效。')});

document.querySelector('#pressure-form').addEventListener('submit',async e=>{
  e.preventDefault();
  const form=new FormData(e.target);
  let bars=[];
  try{bars=JSON.parse(form.get('bars')||'[]')}catch{document.querySelector('#pressure-label').textContent='🔴 JSON无效';document.querySelector('#pressure-reason').textContent='请粘贴标准5分钟bars JSON数组。';return}
  const r=await fetch('/api/pressure-signal',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({pressure:Number(form.get('pressure')),bars})});
  const x=await r.json();
  const icon=x.tone==='green'?'🟢':x.tone==='red'?'🔴':x.tone==='yellow'?'🟡':'⚪';
  document.querySelector('#pressure-label').textContent=`${icon} ${x.label||x.status}`;
  document.querySelector('#pressure-status').textContent=x.label||x.status;
  document.querySelector('#pressure-reason').textContent=x.reason||'';
});
