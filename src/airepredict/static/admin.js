let adminToken='';
async function request(path,method='GET'){
  const response=await fetch(path,{method,headers:{Authorization:'Bearer '+adminToken},cache:'no-store'});
  const body=await response.json();if(!response.ok)throw Error(body.detail||'Operation failed');return body;
}
async function overview(){try{const body=await request('/api/admin/overview');document.getElementById('admin-output').textContent=JSON.stringify(body,null,2);document.getElementById('admin-controls').hidden=false;document.getElementById('admin-notice').textContent='Connected. Operations and results are recorded in the audit.';}catch(error){document.getElementById('admin-notice').textContent=error.message;}}
document.getElementById('admin-login').addEventListener('submit',event=>{event.preventDefault();adminToken=document.getElementById('admin-token').value;document.getElementById('admin-token').value='';overview();});
document.getElementById('admin-refresh').addEventListener('click',overview);
document.getElementById('admin-logout').addEventListener('click',()=>{adminToken='';document.getElementById('admin-output').textContent='';document.getElementById('admin-controls').hidden=true;document.getElementById('admin-notice').textContent='Disconnected.';});
document.querySelectorAll('[data-job]').forEach(button=>button.addEventListener('click',async()=>{
  if(button.dataset.job==='rollback'&&!confirm('Restore the previous compatible model? This changes the active version.'))return;
  try{const job=await request('/api/admin/jobs/'+button.dataset.job,'POST');document.getElementById('admin-notice').textContent='Job accepted: '+job.id;const timer=setInterval(async()=>{try{const result=await request('/api/admin/jobs/'+job.id);document.getElementById('admin-output').textContent=JSON.stringify(result,null,2);if(!['running','queued'].includes(result.status))clearInterval(timer);}catch(error){clearInterval(timer);document.getElementById('admin-notice').textContent=error.message;}},3000);}catch(error){document.getElementById('admin-notice').textContent=error.message;}
}));

fetch('/api/operations').then(r=>r.json()).then(data=>{if(data.managed_by_github){document.getElementById('admin-login').hidden=true;document.getElementById('admin-notice').textContent='Maintenance runs in authenticated GitHub Actions. This free service loads the last published state.';document.getElementById('admin-output').textContent=JSON.stringify(data,null,2);const link=document.createElement('a');link.href=data.workflows_url;link.textContent='Open authenticated maintenance workflows';document.getElementById('admin-notice').appendChild(document.createElement('br'));document.getElementById('admin-notice').appendChild(link);}}).catch(()=>{});
