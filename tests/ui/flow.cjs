const {JSDOM}=require('jsdom');
const path=require('path');
const root=path.resolve(__dirname,'../..');
let activeDom;
const fs=require('fs'),{spawn}=require('child_process'),readline=require('readline'),crypto=require('crypto');
const candidates=[path.join(root,'.venv','Scripts','python.exe'),path.join(root,'.venv','bin','python')];
const python=process.env.PYTHON || candidates.find(p=>fs.existsSync(p)) || (process.platform==='win32'?'python':'python3');
const py=spawn(python,[path.join(__dirname,'bridge.py')]);
py.stderr.on('data',d=>process.stderr.write(d));
const lines=readline.createInterface({input:py.stdout});
const pending=new Map();let counter=0;
let readyResolve;const ready=new Promise(r=>readyResolve=r);
lines.on('line',line=>{const x=JSON.parse(line);if(x.html)readyResolve(x.html);else{const p=pending.get(x.id);pending.delete(x.id);x.error?p.reject(new Error(x.error)):p.resolve(x);}});
function bridge(path,opts={}){const id=++counter;return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});py.stdin.write(JSON.stringify({id,path,...opts})+'\n');});}
async function main(){
 const html=await ready;
 const dom=new JSDOM(html,{url:'http://localhost/',runScripts:'outside-only',pretendToBeVisual:true});
 activeDom=dom;
 const w=dom.window,d=w.document;w.scrollTo=()=>{};
 Object.defineProperty(w,'crypto',{value:crypto.webcrypto});
 w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
 w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
 w.fetch=async(path,opts)=>{const r=await bridge(path,opts);return{ok:r.ok,status:r.status,json:async()=>r.data};};
 const errors=[];w.addEventListener('error',e=>errors.push(e.message));
 w.eval(fs.readFileSync(path.join(root,'static','app.js'),'utf8'));
 const $=s=>d.querySelector(s);
 async function until(fn,label){for(let i=0;i<300;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw new Error('Timeout: '+label+'\n'+d.body.textContent.slice(-1700));}
 function fill(selector,values){const root=$(selector);for(const[k,v]of Object.entries(values)){const el=root.querySelector(`[name="${k}"]`);if(!el)throw new Error('Missing input '+k);el.value=v;el.dispatchEvent(new w.Event('change',{bubbles:true}));}}
 function submit(selector){$(selector).dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));}
 async function save(values){fill('#modal-form',values);submit('#modal-form');await until(()=>!$('#modal').hasAttribute('open')||$('#modal .form-error')?.textContent,'modal result');if($('#modal').hasAttribute('open'))throw new Error($('#modal .form-error').textContent);await new Promise(r=>setTimeout(r,100));}
 function click(s){if(!$(s))throw new Error('Missing '+s);$(s).click();}
 async function nav(p){click(`[data-nav="${p}"]`);await until(()=>$('#breadcrumb').textContent===({transactions:'Giao dịch cá nhân',budgets:'Ngân sách & tiết kiệm',reports:'Báo cáo thống kê',settings:'Cài đặt',groups:'Quỹ nhóm'})[p],p);await new Promise(r=>setTimeout(r,100));}
 await until(()=>!$('#auth').hidden,'initial auth');
 click('#register-tab');fill('#auth-form',{name:'Linh Sinh Viên',email:'linh@example.com',password:'password123'});submit('#auth-form');
 await until(()=>!$('#app').hidden,'register');
 if(!$('#page-content').textContent.includes('0 ₫'))throw new Error('new account not empty');
 click('#add-transaction');await save({type:'income',amount:'5000000',note:'Lương làm thêm'});
 await until(()=>$('#page-content').textContent.includes('5.000.000 ₫'),'income');
 await nav('budgets');click('[data-action="budget"]');await save({limit:'100000',threshold:'80'});
 click('#add-transaction');await save({type:'expense',amount:'80000',note:'Ăn trưa'});
 if(!$('#page-content').textContent.includes('80%'))throw new Error('budget did not update');
 click('[data-action="goal"]');await save({name:'Mua laptop',target:'12000000',deadline:'2027-12-31',auto_percent:'10'});
 click('[data-action="deposit"]');await save({amount:'100000'});
 if(!$('#page-content').textContent.includes('100.000 ₫'))throw new Error('goal did not update');
 await nav('transactions');await until(()=>$('#tx-filters'),'transaction filters');
 if(!$('#page-content').textContent.includes('Ăn trưa'))throw new Error('missing persisted note');
 fill('#tx-filters',{q:'Ăn trưa'});submit('#tx-filters');await until(()=>$('#page-content').textContent.includes('1 giao dịch theo bộ lọc'),'search');
 click('[data-action="edit-tx"]');await save({amount:'85000',note:'Ăn trưa sửa'});
 await nav('reports');await until(()=>$('#page-content').textContent.includes('85.000 ₫'),'report amount');
 await nav('settings');click('[data-action="category"]');await save({name:'Thuốc men',icon:'💊',type:'expense'});
 if(!$('#page-content').textContent.includes('Thuốc men'))throw new Error('custom category missing');
 click('[data-action="wallet"]');await save({name:'Ngân hàng',initial_balance:'250000'});
 click('[data-action="profile"]');await save({name:'Linh Nguyễn',school:'Đại học',student_id:'SV001'});
 await nav('groups');click('[data-action="group"]');await save({name:'Phòng trọ 302'});
 await until(()=>$('#page-content').textContent.includes('MÃ THAM GIA'),'group detail');
 click('[data-action="group-entry"]');await save({kind:'contribution',amount:'100000',note:'Nộp quỹ đầu tháng'});
 if(!$('#page-content').textContent.includes('100.000 ₫'))throw new Error('group balance missing');
 click('[data-action="group-entry"]');await save({kind:'fund_expense',amount:'25000',note:'Nước uống chung'});
 await nav('settings');click('[data-action="logout"]');await until(()=>!$('#auth').hidden&&!$('#auth-submit').disabled,'logout');
 click('#login-tab');fill('#auth-form',{email:'linh@example.com',password:'password123'});submit('#auth-form');await until(()=>!$('#app').hidden,'re-login');
 if(!$('#page-content').textContent.includes('5.065.000 ₫'))throw new Error('balance after re-login wrong');
 // 5m income -85k expense -100k reserved +250k initial = 5.065m.
 if(errors.length)throw new Error(errors.join('\n'));
 console.log('UI integration passed: register, empty state, income/expense, budget, saving, search/edit, reports, category, wallet, profile, group fund, logout/login.');
 dom.window.close();py.stdin.end();
}
main().catch(e=>{console.error(e);if(activeDom)activeDom.window.close();py.stdin.end();process.exitCode=1;});
