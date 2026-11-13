'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = n => new Intl.NumberFormat('vi-VN').format(n || 0) + ' ₫';
const compact = n => n >= 1e9 ? +(n / 1e9).toFixed(1) + ' tỷ' : n >= 1e6 ? +(n / 1e6).toFixed(2) + ' tr' : n >= 1e3 ? +(n / 1e3).toFixed(0) + 'k' : String(n);
const dateVN = d => d ? d.slice(0, 10).split('-').reverse().join('/') : '';
const timeVN = s => new Date(s).toLocaleString('vi-VN', {timeZone:'Asia/Ho_Chi_Minh'});
const priorities = {essential:'Thiết yếu', necessary:'Cần thiết', optional:'Tùy chọn'};
const kinds = {contribution:'Nộp quỹ', fund_expense:'Chi từ quỹ', split:'Ứng tiền & chia đều', settlement:'Thanh toán nợ'};
const colors = ['#2863f4','#00a58a','#f2ad32','#ab82ed','#e96c8a','#58b8ce','#9caac0'];
const meta = {
 dashboard:['Tổng quan','Hôm nay, ví của bạn thế nào?','Quản lý chi tiêu thông minh, dành chỗ cho những điều bạn thích.'],
 transactions:['Giao dịch cá nhân','Từng khoản nhỏ, đều có ý nghĩa.','Ghi lại thu chi và xem tiền của mình đang đi đâu.'],
 budgets:['Ngân sách & tiết kiệm','Chi có kế hoạch. Tiết kiệm có mục tiêu.','Dành đủ cho hôm nay, để dành cho những ngày mai.'],
 groups:['Quỹ nhóm','Tiền chung, rõ ràng cùng nhau.','Quản lý quỹ, chia tiền và đối chiếu khoản nợ của cả nhóm.'],
 reports:['Báo cáo thống kê','Hiểu chiếc ví qua những con số.','Nhìn lại dòng tiền để có những lựa chọn tốt hơn.'],
 settings:['Cài đặt','Không gian của bạn.','Cập nhật tài khoản, quản lý ví và danh mục cá nhân.']
};
let csrf = '', user = null, state = null, page = 'dashboard', authMode = 'login';
let txPage = 1, txFilters = {}, txResult = null, groupId = null, groupData = null;
let reportFilters = {}, reportData = null, renderVersion = 0;
let groupFilters = {kind:'', priority:'', payer:'', sort:'latest'};

function toast(message, kind = '') {
 const el = document.createElement('div'); el.className = 'toast ' + kind; el.textContent = message;
 $('#toasts').append(el); setTimeout(() => el.remove(), kind ? 9000 : 5000);
}
async function api(path, {method = 'GET', body, key} = {}) {
 const headers = {};
 if (method !== 'GET') { headers['X-CSRF-Token'] = csrf; headers['Idempotency-Key'] = key || crypto.randomUUID(); }
 if (body && !(body instanceof FormData)) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(body); }
 let response;
 for (let attempt = 0; attempt < 2; attempt++) {
  try { response = await fetch('/api' + path, {method, headers, body, credentials:'same-origin'}); break; }
  catch (e) { if (attempt) { const error = new Error('Mất kết nối. Hãy thử lưu lại trên cửa sổ này để dùng cùng khóa chống trùng.'); error.network = true; throw error; } }
 }
 const result = await response.json().catch(() => ({error:'Máy chủ chưa xử lý được yêu cầu. Vui lòng thử lại.'}));
 if (!response.ok) {
  if (response.status === 401 && !['/login','/register'].includes(path)) await showAuth();
  throw new Error(result.error || 'Thao tác chưa thành công.');
 }
 return result;
}
function empty(title, description, action = '', label = '') {
 return `<div class="empty"><span>✧</span><b>${esc(title)}</b><p>${esc(description)}</p>${action ? `<button class="btn primary sm" data-action="${esc(action)}">${esc(label)}</button>` : ''}</div>`;
}
function progress(percent, cls = '') { return `<div class="progress ${cls}"><span style="width:${Math.max(0, Math.min(100, percent || 0))}%"></span></div>`; }
function budgetClass(b) { return b.percent >= 100 ? 'danger' : b.percent >= b.threshold ? 'warn' : 'green'; }
function options(items, selected, label = 'name') { return items.map(i => `<option value="${i.id}" ${String(i.id) === String(selected) ? 'selected' : ''}>${esc(i[label])}</option>`).join(''); }
function periodBounds(month = $('#month').value) {
 const [y,m] = month.split('-').map(Number);
 return {start:month + '-01', end:month + '-' + String(new Date(y, m, 0).getDate()).padStart(2,'0')};
}
function filterQuery(filters) { return new URLSearchParams(Object.entries(filters).filter(([,v]) => v !== '' && v != null)).toString(); }
function statsHTML(income = state.income, expense = state.expense) {
 return `<div class="stats"><div class="stat"><span class="stat-label">Số dư khả dụng</span><span class="stat-icon">▣</span><strong>${money(state.balance)}</strong><small>Sẵn sàng cho kế hoạch của bạn</small></div><div class="stat"><span class="stat-label">Tổng thu trong kỳ</span><span class="stat-icon">↗</span><strong>${money(income)}</strong><small>Học bổng, làm thêm & khoản thu</small></div><div class="stat"><span class="stat-label">Tổng chi trong kỳ</span><span class="stat-icon">⇄</span><strong>${money(expense)}</strong><small>Chưa bao gồm chuyển vào hũ tiết kiệm</small></div><div class="stat"><span class="stat-label">Tổng tiết kiệm</span><span class="stat-icon">♙</span><strong>${money(state.saved)}</strong><small>Đang tích lũy trong ${state.goals.length} hũ</small></div></div>`;
}
function barChart(rows, comparison = false) {
 if (!rows.length || !rows.some(r => r.expense || r.income)) return empty('Chưa có dòng tiền trong kỳ này', 'Thêm khoản thu đầu tiên để bắt đầu theo dõi chiếc ví.', 'transaction', '＋ Ghi giao dịch');
 rows = rows.slice(-24);
 const max = Math.max(...rows.map(r => Math.max(r.expense, comparison ? r.income : 0)), 1) * 1.15;
 const width = 620, height = 215, left = 48, right = 10, top = 20, bottom = 34, plot = height-top-bottom;
 const unit = (width-left-right) / rows.length;
 let svg = `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Biểu đồ ${comparison?'thu nhập và chi tiêu':'chi tiêu'} theo thời gian"><title>Dòng tiền theo thời gian</title>`;
 for (let n = 0; n <= 4; n++) { const y = top+plot-n*plot/4; svg += `<line class="gridline" x1="${left}" x2="${width-right}" y1="${y}" y2="${y}"/><text x="${left-8}" y="${y+3}" text-anchor="end">${compact(max*n/4)}</text>`; }
 rows.forEach((r,i) => {
  const x=left+unit*i+unit/2, bw=Math.min(40,unit*(comparison?.3:.43));
  const h=r.expense/max*plot;
  if (comparison) {const ih=r.income/max*plot;svg+=`<rect x="${x-bw-2}" y="${top+plot-ih}" width="${bw}" height="${ih}" rx="4" fill="#00a58a"><title>Thu: ${money(r.income)}</title></rect>`;}
  svg+=`<rect x="${comparison?x+2:x-bw/2}" y="${top+plot-h}" width="${bw}" height="${h}" rx="4" fill="${comparison||i===rows.length-1?'#2863f4':'#bed1f8'}"><title>Chi: ${money(r.expense)}</title></rect>`;
  if (!comparison && rows.length <= 8) svg+=`<text class="value" x="${x}" y="${top+plot-h-8}" text-anchor="middle">${compact(r.expense)}</text>`;
  let label=r.month?'T'+Number(r.month.slice(5)):r.label;
  if (label?.length===10) label=dateVN(label).slice(0,5);
  if (rows.length<=12||i%Math.ceil(rows.length/8)===0) svg+=`<text x="${x}" y="${height-10}" text-anchor="middle">${esc(label)}</text>`;
 });
 return svg+'</svg>';
}
function txTable(rows, editable = false) {
 if (!rows.length) return empty('Chưa có giao dịch', 'Thêm khoản thu hoặc đổi bộ lọc để xem dữ liệu.', 'transaction', '＋ Thêm giao dịch');
 return `<div class="table-wrap"><table><thead><tr><th>Giao dịch</th><th>Danh mục</th><th>Ngày</th>${editable?'<th>Ví / ưu tiên</th>':''}<th class="money">Số tiền</th>${editable?'<th></th>':''}</tr></thead><tbody>${rows.map(t=>`<tr><td><div class="transaction-name"><span>${esc(t.icon)}</span><div>${esc(t.note || t.category)}${editable?`<small>${{cash:'Tiền mặt',bank:'Chuyển khoản',ewallet:'Ví điện tử'}[t.payment_method]}</small>`:''}</div></div></td><td><span class="badge ${t.type==='income'?'income':''}">${esc(t.category)}</span></td><td class="muted">${dateVN(t.date)}</td>${editable?`<td>${esc(t.wallet)}<small style="display:block;margin-top:5px">${priorities[t.priority]}</small></td>`:''}<td class="money ${t.type==='income'?'positive':''}">${t.type==='income'?'+':'−'}${money(t.amount)}</td>${editable?`<td><div class="action-buttons"><button data-action="edit-tx" data-id="${t.id}" aria-label="Sửa giao dịch">Sửa</button><button class="delete" data-action="delete-tx" data-id="${t.id}" aria-label="Xóa giao dịch">Xóa</button></div></td>`:''}</tr>`).join('')}</tbody></table></div>`;
}
function dashboardHTML() {
 const budgets=state.budgets, total=budgets.find(b=>!b.category_id)||budgets[0];
 return statsHTML()+`<div class="dashboard-grid"><div class="stack"><section class="card"><div class="card-head"><div><h3>Dòng tiền của bạn</h3><small>Chi tiêu trong 6 tháng gần đây</small></div><span class="legend"><span><b></b>Khoản chi</span></span></div>${barChart(state.trend)}</section><section class="card"><div class="card-head"><h3>Giao dịch gần đây</h3><button class="text-button" data-nav="transactions">Xem tất cả →</button></div>${txTable(state.recent)}</section></div><div class="stack"><section class="card"><div class="card-head"><h3>Ngân sách trong kỳ</h3><button class="text-button" data-nav="budgets">Chỉnh sửa</button></div>${total?`<div class="budget-total"><div><strong>${money(total.spent)}</strong> <small>/ ${money(total.limit)}</small></div><span class="badge ${budgetClass(total)}">${total.percent}%</span></div>${progress(total.percent,budgetClass(total))}<div class="notice ${total.percent>=100?'danger':''}">${esc(total.name)} · ${total.remaining>=0?'Còn '+money(total.remaining)+' để chi':'Vượt '+money(-total.remaining)}</div>${budgets.filter(b=>b!==total).slice(0,4).map(b=>`<div class="mini-budget"><span>${esc(b.name)}</span>${progress(b.percent,budgetClass(b))}<small>${b.percent}%</small></div>`).join('')}`:empty('Lên kế hoạch chi tiêu','Đặt ngân sách đầu tiên để nhận cảnh báo.','budget','＋ Đặt ngân sách')}</section><section class="card"><div class="card-head"><h3>Hũ tiết kiệm</h3><button class="text-button" data-action="goal">＋ Tạo hũ</button></div>${state.goals.length?state.goals.slice(0,3).map(g=>`<div class="goal-mini"><span>♙</span><div><b>${esc(g.name)}</b><small>${money(g.saved)} / ${money(g.target)}</small></div>${progress(g.saved/g.target*100,'green')}<small>${Math.round(g.saved/g.target*100)}%</small></div>`).join(''):empty('Ước mơ bắt đầu từ một hũ nhỏ','Laptop mới, học phí hay chuyến đi tiếp theo?','goal','Tạo mục tiêu')}</section><section class="card"><div class="card-head"><h3>Quỹ nhóm</h3><button class="text-button" data-nav="groups">${state.groups.length} quỹ →</button></div>${state.groups.length?state.groups.slice(0,2).map(g=>`<div class="group-mini"><b>♧</b><div><strong>${esc(g.name)}</strong><small>Số dư ${money(g.cash)} · ${g.members} thành viên</small></div><button class="text-button" data-action="open-group" data-id="${g.id}">→</button></div>`).join(''):empty('Cùng nhau chi tiêu minh bạch','Tạo quỹ cho phòng trọ, lớp hoặc chuyến đi.','group','＋ Tạo nhóm')}</section></div></div>`;
}
function filtersHTML(values, report = false) {
 return `<form class="filters" id="${report?'report':'tx'}-filters"><label>Từ ngày<input type="date" name="start" value="${esc(values.start||'')}"></label><label>Đến ngày<input type="date" name="end" value="${esc(values.end||'')}"></label>${report?`<label>Gộp theo<select name="period"><option value="day" ${values.period==='day'?'selected':''}>Ngày</option><option value="week" ${values.period==='week'?'selected':''}>Tuần (thứ Hai)</option><option value="month" ${values.period==='month'?'selected':''}>Tháng</option><option value="year" ${values.period==='year'?'selected':''}>Năm</option></select></label>`:`<label>Loại<select name="type"><option value="">Tất cả</option><option value="income" ${values.type==='income'?'selected':''}>Thu nhập</option><option value="expense" ${values.type==='expense'?'selected':''}>Chi tiêu</option></select></label>`}<label>Danh mục<select name="category"><option value="">Tất cả danh mục</option>${options(state.categories,values.category)}</select></label>${!report?`<label>Tìm nội dung<input name="q" value="${esc(values.q||'')}" placeholder="Ghi chú, danh mục…"></label>`:''}<button class="btn primary">Áp dụng</button><button class="btn" type="button" data-action="${report?'report':'tx'}-all">Toàn bộ</button></form>`;
}
function transactionsHTML() {
 return filtersHTML(txFilters)+`<section class="card"><div class="card-head"><h3>Lịch sử giao dịch <small>${txResult.total} giao dịch theo bộ lọc</small></h3><a class="btn sm" href="/api/export?${filterQuery(txFilters)}">↓ Xuất CSV</a></div>${txTable(txResult.items,true)}<div class="pagination"><button class="btn sm" data-action="prev-page" ${txPage<=1?'disabled':''}>← Trước</button><span>Trang ${txPage} / ${txResult.pages}</span><button class="btn sm" data-action="next-page" ${txPage>=txResult.pages?'disabled':''}>Sau →</button></div></section>`;
}
function budgetsHTML() {
 return `<div class="toolbar"><h2>Ngân sách trong tháng đang chọn</h2><button class="btn primary" data-action="budget">＋ Đặt ngân sách</button></div>${state.budgets.length?`<div class="card-grid">${state.budgets.map(b=>`<section class="card budget-card"><div class="card-head"><h3>${esc(b.name)}</h3><div class="action-buttons"><button data-action="edit-budget" data-id="${b.id}">Sửa</button><button class="delete" data-action="delete-budget" data-id="${b.id}">Xóa</button></div></div><div class="budget-total"><strong>${money(b.spent)}</strong><span class="badge ${budgetClass(b)}">${b.percent}%</span></div><small>Hạn mức ${money(b.limit)}</small>${progress(b.percent,budgetClass(b))}<div class="notice ${b.remaining<0?'danger':'info'}">${b.remaining<0?'Đã vượt '+money(-b.remaining):'Còn lại '+money(b.remaining)}</div><small>${b.alerts_enabled?'Thông báo khi đạt '+b.threshold+'%':'Đã tắt thông báo'}</small><div class="budget-dates">${dateVN(b.start)} — ${dateVN(b.end)}</div></section>`).join('')}</div>`:`<div class="card">${empty('Tháng này chưa có ngân sách','Bạn có thể đặt hạn mức cho một ngày, tuần hoặc cả tháng.','budget','＋ Lập ngân sách')}</div>`}<div class="toolbar section-gap"><div><h2>Hũ tiết kiệm của bạn</h2><p class="form-hint">Tiền chuyển vào hũ được tách khỏi số dư khả dụng, không tính là chi tiêu.</p></div><button class="btn primary" data-action="goal">＋ Tạo hũ mới</button></div>${state.goals.length?`<div class="card-grid">${state.goals.map(g=>`<section class="card goal-card"><div class="card-head"><span class="goal-title">♙</span><div class="action-buttons"><button data-action="edit-goal" data-id="${g.id}">Sửa</button><button class="delete" data-action="delete-goal" data-id="${g.id}">Xóa</button></div></div><h3>${esc(g.name)}</h3><small>Hoàn thành trước ${dateVN(g.deadline)}</small><div class="goal-amount">${money(g.saved)} <small>/ ${money(g.target)}</small></div>${progress(g.saved/g.target*100,'green')}<small>${Math.round(g.saved/g.target*100)}% · Còn thiếu ${money(Math.max(0,g.target-g.saved))}</small><div class="card-actions"><button class="btn primary sm" data-action="deposit" data-id="${g.id}">＋ Nạp hũ</button><button class="btn sm" data-action="withdraw" data-id="${g.id}">Rút tiền</button><button class="btn ghost sm" data-action="goal-history" data-id="${g.id}">Lịch sử</button></div><p class="form-hint" style="margin:15px 0 0">Gợi ý trích ${g.auto_percent}% từ thu nhập mới</p></section>`).join('')}</div>`:`<div class="card">${empty('Bạn muốn để dành cho điều gì?','Tạo một mục tiêu, đặt hạn hoàn thành và tích lũy từng chút.','goal','Tạo hũ đầu tiên')}</div>`}`;
}
function groupsHTML() {
 if (groupData) return groupDetailHTML();
 return `<div class="toolbar"><h2>Những quỹ bạn tham gia</h2><div class="inline-actions"><button class="btn" data-action="join-group">Nhập mã tham gia</button><button class="btn primary" data-action="group">＋ Tạo nhóm</button></div></div><div class="notice info">Quỹ chung và khoản ứng tiền được theo dõi riêng. Trưởng nhóm xác nhận nộp quỹ, chi quỹ và trả nợ. Thành viên có thể ghi khoản mình ứng tiền.</div>${state.groups.length?`<div class="card-grid">${state.groups.map(g=>`<section class="card group-card"><div class="group-icon">♧</div><h3>${esc(g.name)}</h3><small>${g.members} thành viên · ${g.role==='admin'?'Trưởng nhóm':'Thành viên'}</small><div class="summary-strip"><div><small>Số dư quỹ</small><strong>${money(g.cash)}</strong></div><div><small>Tổng chi</small><strong>${money(g.expense)}</strong></div></div><button class="btn" data-action="open-group" data-id="${g.id}">Mở quỹ nhóm →</button></section>`).join('')}</div>`:`<div class="card">${empty('Kết nối để cùng quản lý tiền','Bạn đã có mã nhóm? Nhập mã để cùng theo dõi quỹ chung.','group','＋ Tạo nhóm đầu tiên')}</div>`}`;
}
function groupDetailHTML() {
 const g=groupData, people=Object.fromEntries(g.members.map(m=>[m.id,m.name]));
 const rank={essential:0,necessary:1,optional:2};
 const entries=g.entries.filter(e=>(!groupFilters.kind||e.kind===groupFilters.kind)&&(!groupFilters.priority||e.priority===groupFilters.priority)&&(!groupFilters.payer||e.payer_id===Number(groupFilters.payer)));
 entries.sort((a,b)=>groupFilters.sort==='priority'?rank[a.priority]-rank[b.priority]||b.id-a.id:groupFilters.sort==='amount'?b.amount-a.amount:b.date.localeCompare(a.date)||b.id-a.id);
 return `<div class="toolbar"><button class="text-button" data-action="back-groups">← Tất cả quỹ nhóm</button><div class="inline-actions"><button class="btn" data-action="refresh-group">↻ Cập nhật</button><button class="btn primary" data-action="group-entry">＋ Ghi giao dịch nhóm</button></div></div><section class="card"><div class="card-head"><div><h2 style="margin:0 0 7px">${esc(g.name)}</h2><small>${g.members.length} thành viên · Tự làm mới mỗi 15 giây khi đang mở</small></div><span class="badge">${g.role==='admin'?'Trưởng nhóm':'Thành viên'}</span></div><div class="summary-strip"><div><small>Tiền còn trong quỹ</small><strong>${money(g.cash)}</strong></div><div><small>Tổng đã chi</small><strong>${money(g.expense)}</strong></div><div><small>Tổng nợ chưa trả</small><strong>${money(g.members.reduce((s,m)=>s+Math.max(0,-m.balance),0))}</strong></div></div><div class="code-box section-gap"><small>MÃ THAM GIA</small><code>${esc(g.code)}</code><button class="text-button" data-action="copy-code">Sao chép</button>${g.role==='admin'?'<button class="text-button" data-action="rotate-code">Đổi mã</button>':''}</div></section><div class="two-col section-gap"><section class="card"><div class="card-head"><h3>Thành viên & đóng góp</h3></div><div class="member-list">${g.members.map(m=>`<div class="member-row"><span class="avatar">${esc(m.name[0])}</span><div>${esc(m.name)} ${m.role==='admin'?'<span class="badge">Trưởng nhóm</span>':''}<small>Nộp quỹ ${money(m.contribution)} · Đã ứng ${money(m.paid)}</small></div><b class="${m.balance<0?'negative':'positive'}">${m.balance<0?'Nợ ':m.balance>0?'Nhận ':''}${money(Math.abs(m.balance))}</b></div>`).join('')}</div><div class="notice info">Nộp quỹ là khoản đóng góp chung, không tự tạo nợ. Dư nợ phát sinh từ các khoản ứng tiền chia đều và thanh toán nợ.</div></section><section class="card"><div class="card-head"><h3>Gợi ý thanh toán nợ ròng</h3></div>${g.settlements.length?g.settlements.map((s,i)=>`<div class="settlement"><p>${esc(people[s.from])} → ${esc(people[s.to])}<small>${money(s.amount)}</small></p>${g.role==='admin'?`<button class="btn sm" data-action="settle" data-id="${i}">Ghi nhận đã trả</button>`:''}</div>`).join(''):empty('Không còn khoản nợ nào','Các khoản ứng tiền đã được cân đối.')}<p class="form-hint">Gợi ý dựa trên nợ ròng. Chỉ xác nhận sau khi đã chuyển tiền thực tế.</p></section></div><section class="card section-gap"><div class="card-head"><h3>Sao kê nhóm <small>200 giao dịch gần nhất · Các khoản hủy được giữ để đối chiếu</small></h3><button class="text-button" data-action="group-entry">＋ Thêm khoản</button></div>${groupFilterHTML(g)}${entries.length?`<div class="table-wrap"><table><thead><tr><th>Ngày / người ghi</th><th>Nội dung</th><th>Người thanh toán</th><th>Loại</th><th class="money">Số tiền</th><th>Chứng từ</th><th></th></tr></thead><tbody>${entries.map(e=>`<tr class="${e.voided?'voided':''}"><td>${dateVN(e.date)}<small style="display:block;margin-top:5px">${esc(e.actor)} · ${timeVN(e.time)}</small></td><td>${esc(e.note)}<small style="display:block;margin-top:5px">${priorities[e.priority]}${e.shares.length?' · '+e.shares.map(s=>esc(s.name)+': '+money(s.amount)).join(', '):''}</small></td><td>${esc(e.payer)}${e.receiver?'<small style="display:block;margin-top:5px">→ '+esc(e.receiver)+'</small>':''}</td><td><span class="badge ${e.kind==='contribution'?'income':''}">${kinds[e.kind]}</span>${e.voided?'<small> Đã hủy</small>':''}</td><td class="money">${money(e.amount)}</td><td>${e.receipt?`<a href="/api/groups/${g.id}/entries/${e.id}/receipt">↓ Hóa đơn</a>`:!e.voided&&(g.role==='admin'||e.actor_id===user.id)?`<button class="text-button" data-action="receipt" data-id="${e.id}">＋ Thêm</button>`:'—'}</td><td>${g.role==='admin'&&!e.voided?`<button class="text-button negative" data-action="void-entry" data-id="${e.id}">Hủy</button>`:''}</td></tr>`).join('')}</tbody></table></div>`:empty('Quỹ nhóm chưa có giao dịch','Bắt đầu bằng khoản nộp quỹ hoặc một khoản ứng tiền.','group-entry','Ghi giao dịch')}</section><section class="card section-gap"><div class="card-head"><h3>Lịch sử kiểm tra</h3><small>100 hoạt động gần nhất</small></div>${g.audit.map(a=>`<div class="audit"><b>${esc(a.actor)}</b> · ${esc(auditLabel(a.action))}<small>${timeVN(a.time)}${a.details.reason?' · Lý do: '+esc(a.details.reason):''}${a.details.amount?' · '+money(a.details.amount):''}${a.details.id?' · Mã #'+a.details.id:''}</small></div>`).join('')}</section>`;
}
function groupFilterHTML(g){
 return `<form id="group-filters" class="filters" style="padding:0"><label>Loại khoản<select name="kind"><option value="">Tất cả</option>${Object.entries(kinds).map(([v,l])=>`<option value="${v}" ${groupFilters.kind===v?'selected':''}>${l}</option>`).join('')}</select></label><label>Ưu tiên<select name="priority"><option value="">Tất cả</option>${Object.entries(priorities).map(([v,l])=>`<option value="${v}" ${groupFilters.priority===v?'selected':''}>${l}</option>`).join('')}</select></label><label>Người thanh toán<select name="payer"><option value="">Tất cả</option>${options(g.members,groupFilters.payer)}</select></label><label>Sắp xếp<select name="sort"><option value="latest" ${groupFilters.sort==='latest'?'selected':''}>Ngày mới nhất</option><option value="priority" ${groupFilters.sort==='priority'?'selected':''}>Ưu tiên thiết yếu trước</option><option value="amount" ${groupFilters.sort==='amount'?'selected':''}>Số tiền giảm dần</option></select></label><button class="btn sm">Lọc</button></form>`;
}
function auditLabel(action) {return ({'group.create':'Tạo nhóm','group.join':'Tham gia nhóm','group.rotate_code':'Đổi mã tham gia','group.entry.create':'Ghi giao dịch','group.entry.void':'Hủy giao dịch','group.receipt.add':'Đính kèm hóa đơn'})[action]||action;}
function reportsHTML() {
 const r=reportData; let accumulator=0;
 const gradient=r.categories.map((c,i)=>{const from=accumulator;accumulator+=c.amount/r.expense*100;return `${colors[i%colors.length]} ${from}% ${accumulator}%`;}).join(',');
 return `<div class="toolbar"><div class="inline-actions"><button class="btn sm" data-action="report-today">Hôm nay</button><button class="btn sm" data-action="report-week">Tuần này</button><button class="btn sm" data-action="report-month">Tháng đang chọn</button><button class="btn sm" data-action="report-year">Năm đang chọn</button></div><a class="btn sm" href="/api/export?${filterQuery(reportFilters)}">↓ Tải CSV</a></div>${filtersHTML(reportFilters,true)}<section class="card"><div class="summary-strip"><div><small>Tổng thu</small><strong class="positive">${money(r.income)}</strong></div><div><small>Tổng chi</small><strong>${money(r.expense)}</strong></div><div><small>Chênh lệch thu − chi</small><strong class="${r.net<0?'negative':'positive'}">${money(r.net)}</strong></div><div><small>Số giao dịch</small><strong>${r.count}</strong></div></div><p class="form-hint" style="margin:20px 0 0">Chênh lệch trong kỳ không bao gồm số dư ban đầu và chuyển hũ. Số dư khả dụng hiện tại: ${money(state.balance)}.</p></section><div class="two-col section-gap"><section class="card"><div class="card-head"><h3>Thu nhập & chi tiêu</h3><div class="legend"><span><b style="background:var(--green)"></b>Thu</span><span><b></b>Chi</span></div></div>${barChart(r.timeline,true)}${r.timeline.length>24?'<small>Biểu đồ hiển thị 24 kỳ gần nhất; tổng số và CSV bao gồm toàn bộ bộ lọc.</small>':''}</section><section class="card"><div class="card-head"><h3>Chi tiêu theo danh mục</h3></div>${r.categories.length?`<div class="distribution"><div class="donut" style="background:conic-gradient(${gradient})" role="img" aria-label="Phân bổ chi tiêu theo danh mục"><span>Tổng chi<b>${compact(r.expense)} ₫</b></span></div><div class="distribution-legend">${r.categories.map((c,i)=>`<div class="distribution-row"><i style="background:${colors[i%colors.length]}"></i><span>${esc(c.name)}<small style="display:block;margin-top:4px">${Math.round(c.amount/r.expense*100)}%</small></span><strong>${money(c.amount)}</strong></div>`).join('')}</div></div>`:empty('Chưa có khoản chi trong kỳ','Biểu đồ sẽ xuất hiện khi bạn ghi chi tiêu.')}</section></div><section class="card section-gap"><div class="card-head"><h3>So sánh chi tiêu giữa các tháng</h3><small>6 tháng đến tháng đang chọn</small></div>${barChart(state.trend)}</section><div class="two-col section-gap"><section class="card"><div class="card-head"><h3>Những khoản chi lớn nhất</h3></div>${txTable(r.top)}</section><section class="card"><div class="card-head"><h3>Thói quen chi tiêu trong kỳ</h3></div>${Object.entries(priorities).map(([key,label])=>{const amount=r.priorities[key]||0;return `<div class="budget-total" style="margin-top:20px"><span>${label}</span><small>${money(amount)} · ${r.expense?Math.round(amount/r.expense*100):0}%</small></div>${progress(r.expense?amount/r.expense*100:0,key==='optional'?'warn':'green')}`;}).join('')}<div class="notice info">${r.expense?'Khoản tùy chọn chiếm '+Math.round((r.priorities.optional||0)/r.expense*100)+'% chi tiêu. Bạn có thể thử dành một phần khoản này cho mục tiêu tiết kiệm.':'Bắt đầu ghi giao dịch để hiểu thói quen chi tiêu của mình.'}</div></section></div>`;
}
function settingsHTML() {
 return `<div class="two-col"><section class="card"><div class="card-head"><h3>Thông tin sinh viên</h3><button class="text-button" data-action="profile">Chỉnh sửa</button></div><div class="settings-list"><div class="settings-row"><span>Họ và tên</span><b>${esc(user.name)}</b></div><div class="settings-row"><span>Email</span><b>${esc(user.email)}</b></div><div class="settings-row"><span>Trường</span><b>${esc(user.school||'Chưa cập nhật')}</b></div><div class="settings-row"><span>Mã sinh viên</span><b>${esc(user.student_id||'Chưa cập nhật')}</b></div></div><button class="btn danger section-gap" data-action="logout">Đăng xuất</button></section><section class="card"><div class="card-head"><h3>Ví & nguồn tiền</h3><button class="text-button" data-action="wallet">＋ Thêm ví</button></div><div class="settings-list">${state.wallets.map(w=>`<div class="settings-row"><span>▣</span><div><b>${esc(w.name)}</b><small>Khả dụng ${money(w.balance)} · Ban đầu ${money(w.initial_balance)}</small></div><div class="action-buttons"><button data-action="edit-wallet" data-id="${w.id}">Đổi tên</button><button class="delete" data-action="delete-wallet" data-id="${w.id}">Xóa</button></div></div>`).join('')}</div><p class="form-hint">Ví có giao dịch được giữ lại để bảo đảm lịch sử. Muốn tăng số dư, hãy thêm giao dịch thu.</p></section></div><section class="card section-gap"><div class="card-head"><h3>Danh mục thu / chi</h3><button class="btn primary sm" data-action="category">＋ Thêm danh mục</button></div><div class="category-list">${state.categories.map(c=>`<div class="category-row"><span>${esc(c.icon)}</span><div>${esc(c.name)}<small>${c.type==='income'?'Thu nhập':'Chi tiêu'}</small></div><button data-action="edit-category" data-id="${c.id}" aria-label="Sửa danh mục">Sửa</button><button data-action="delete-category" data-id="${c.id}" aria-label="Xóa danh mục">×</button></div>`).join('')}</div></section>`;
}
async function refresh() {
 state=await api('/state?month='+$('#month').value);
 $('#group-count').textContent=state.groups.length;
 $('#notification-dot').hidden=!state.warnings.length;
 $('#user-name').textContent='Chào, '+user.name.split(' ').at(-1);
 $('#user-avatar').textContent=user.name[0].toUpperCase();
 await render();
}
async function render() {
 const version=++renderVersion;
 const m=meta[page]; $('#breadcrumb').textContent=m[0]; $('#page-title').textContent=m[1]; $('#page-description').textContent=m[2];
 $$('.nav-item[data-nav]').forEach(n=>n.classList.toggle('active',n.dataset.nav===page));
 let content;
 if(page==='transactions'){txResult=await api('/transactions?'+filterQuery({...txFilters,page:txPage}));content=transactionsHTML();}
 else if(page==='reports'){reportData=await api('/reports?'+filterQuery(reportFilters));content=reportsHTML();}
 else if(page==='groups'){if(groupId) groupData=await api('/groups/'+groupId);content=groupsHTML();}
 else content=({dashboard:dashboardHTML,budgets:budgetsHTML,settings:settingsHTML})[page]();
 if(version!==renderVersion) return;
 $('#page-content').innerHTML=content;
 const gf=$('#group-filters');if(gf)gf.addEventListener('submit',e=>{e.preventDefault();groupFilters=Object.fromEntries(new FormData(gf));safeRender();});
 const txForm=$('#tx-filters'); if(txForm) txForm.addEventListener('submit',e=>{e.preventDefault();txFilters=Object.fromEntries(new FormData(txForm));txPage=1;safeRender();});
 const rf=$('#report-filters'); if(rf) rf.addEventListener('submit',e=>{e.preventDefault();reportFilters=Object.fromEntries(new FormData(rf));safeRender();});
}
function safeRender(){render().catch(e=>toast(e.message,'error'));}
async function navigate(next) {
 page=next;$('#sidebar').classList.remove('open');
 if(page==='transactions'&&!Object.keys(txFilters).length) txFilters=periodBounds();
 if(page==='reports'&&!Object.keys(reportFilters).length) reportFilters={...periodBounds(),period:'day'};
 await render(); window.scrollTo({top:0,behavior:'smooth'});
}
async function showAuth(){
 $('#auth-submit').disabled=true;
 user=null;state=null;$('#app').hidden=true;$('#auth').hidden=false;$('#loading').hidden=true;
 // Logout clears the session, so obtain a fresh CSRF token before the next login.
 try{const r=await api('/auth');csrf=r.csrf;}catch(e){toast(e.message,'error');}finally{$('#auth-submit').disabled=false;}
}
function modal(title,body){$('#modal-title').textContent=title;$('#modal-body').innerHTML=body;if(!$('#modal').open)$('#modal').showModal();}
function closeModal(){$('#modal').close();}
function formModal(title,fields,save,label='Lưu thông tin',init){
 modal(title,`<form id="modal-form">${fields}<p class="form-error" role="alert"></p><div class="form-actions"><button type="button" class="btn" data-action="close">Hủy</button><button class="btn primary" type="submit">${label}</button></div></form>`);
 const form=$('#modal-form');if(init)init(form);
 form.addEventListener('submit',async e=>{
  e.preventDefault();if(form.dataset.busy)return;form.dataset.busy='1';
  const button=$('button[type=submit]',form);button.disabled=true;$('.form-error',form).textContent='';
  form.dataset.key ||= crypto.randomUUID();
  try{const result=await save(Object.fromEntries(new FormData(form)),form,form.dataset.key);closeModal();await refresh();toast('Đã lưu thông tin.');if(result?.warnings?.length)toast(result.warnings.map(b=>`${b.name}: đã dùng ${b.percent}% ngân sách`).join(' · '),'warning');}
  catch(error){if(!error.network)delete form.dataset.key;$('.form-error',form).textContent=error.message;}
  finally{delete form.dataset.busy;button.disabled=false;}
 });
}
function confirmAction(title,message,action){formModal(title,`<p class="form-hint">${esc(message)}</p>`,(_,f,key)=>action(key),'Xác nhận');}
function transactionModal(t=null) {
 const income=t?.type==='income';
 formModal(t?'Sửa giao dịch':'Thêm một giao dịch',`<div class="form-grid"><label>Loại giao dịch<select name="type"><option value="expense" ${!income?'selected':''}>− Chi tiêu</option><option value="income" ${income?'selected':''}>＋ Thu nhập</option></select></label><label>Số tiền (VND)<input name="amount" type="number" min="1" max="1000000000000" step="1" required value="${t?.amount||''}" placeholder="Ví dụ: 45000"></label><label>Danh mục<select name="category_id" required></select></label><label>Ví / nguồn tiền<select name="wallet_id" required>${options(state.wallets,t?.wallet_id)}</select></label><label>Ngày giao dịch<input name="date" type="date" required value="${t?.date||state.today}" max="${state.today}"></label><label>Phương thức<select name="payment_method">${Object.entries({cash:'Tiền mặt',bank:'Chuyển khoản ngân hàng',ewallet:'Ví điện tử'}).map(([v,l])=>`<option value="${v}" ${t?.payment_method===v?'selected':''}>${l}</option>`).join('')}</select></label><label class="wide">Mức ưu tiên<select name="priority">${Object.entries(priorities).map(([v,l])=>`<option value="${v}" ${(t?.priority||'necessary')===v?'selected':''}>${l}</option>`).join('')}</select></label><label class="wide">Ghi chú<input name="note" maxlength="500" value="${esc(t?.note||'')}" placeholder="Bạn đã dùng khoản tiền này cho điều gì?"></label></div><div id="allocations"></div>${t?'<p class="form-hint">Khi sửa khoản thu, trích lập cũ được hoàn lại và thay bằng lựa chọn mới bên trên. Nếu hũ đã dùng khoản trích đó, thao tác sẽ bị chặn.</p>':''}`,
 async(p,form,key)=>{
  const allocations=$$('.allocation-check:checked',form).map(c=>({goal_id:Number(c.value),amount:Number($('#allocation-'+c.value,form).value)}));
  return api('/transactions'+(t?'/'+t.id:''),{method:t?'PATCH':'POST',body:{...p,allocations},key});
 },'Lưu giao dịch',form=>{
  const kind=$('[name=type]',form), cats=$('[name=category_id]',form), amount=$('[name=amount]',form);
  function updateCats(){cats.innerHTML=options(state.categories.filter(c=>c.type===kind.value),t?.category_id);updateAllocation();}
  function updateAllocation(){
   $('#allocations').innerHTML=kind.value==='income'&&state.goals.length?`<div class="notice info">Đề xuất trích 5–20% vào hũ tiết kiệm. Đánh dấu hũ bạn muốn trích; tổng trích không vượt thu nhập.</div>${state.goals.filter(g=>g.saved<g.target).map(g=>`<div class="allocation-row"><label class="check-label"><input class="allocation-check" type="checkbox" value="${g.id}"><span>${esc(g.name)}<small>Gợi ý ${g.auto_percent}% thu nhập</small></span></label><input id="allocation-${g.id}" aria-label="Số tiền trích cho ${esc(g.name)}" type="number" min="1" step="1" value="${Math.max(1,Math.min(g.target-g.saved,Math.floor(Number(amount.value||0)*g.auto_percent/100)))}"></div>`).join('')}`:'';
  }
  kind.addEventListener('change',updateCats);amount.addEventListener('input',updateAllocation);updateCats();
 });
}
function budgetModal(b=null){
 const bounds=periodBounds();
 formModal(b?'Sửa ngân sách':'Lên kế hoạch ngân sách',`<div class="form-grid"><label class="wide">Phạm vi<select name="category_id"><option value="">Tổng chi tiêu</option>${options(state.categories.filter(c=>c.type==='expense'),b?.category_id)}</select></label><label class="wide">Hạn mức (VND)<input name="limit" type="number" min="1" max="1000000000000" required value="${b?.limit||''}" placeholder="Ví dụ: 3000000"></label><label>Từ ngày<input type="date" name="start" required value="${b?.start||bounds.start}"></label><label>Đến ngày<input type="date" name="end" required value="${b?.end||bounds.end}"></label><label class="wide">Ngưỡng cảnh báo (%)<input name="threshold" type="number" min="1" max="100" value="${b?.threshold||80}" required></label></div><label class="check-label"><input type="checkbox" name="alerts_enabled" ${b?.alerts_enabled===false?'':'checked'}>Hiển thị thông báo khi chạm ngưỡng</label><p class="form-hint">Chọn cùng một ngày để đặt ngân sách ngày; chọn 7 ngày cho ngân sách tuần. Chi tiêu trong khoảng ngày được tính tự động.</p>`,(p,f,key)=>api('/budgets'+(b?'/'+b.id:''),{method:b?'PATCH':'POST',body:{...p,category_id:p.category_id||null,alerts_enabled:$('[name=alerts_enabled]',f).checked},key}));
}
function goalModal(g=null){formModal(g?'Sửa mục tiêu':'Tạo hũ tiết kiệm',`<label>Tên mục tiêu<input name="name" required maxlength="100" value="${esc(g?.name||'')}" placeholder="Mua laptop, học phí kỳ tới…"></label><div class="form-grid"><label>Số tiền mục tiêu (VND)<input name="target" type="number" min="1" max="1000000000000" required value="${g?.target||''}"></label><label>Hạn hoàn thành<input name="deadline" type="date" required value="${g?.deadline||''}"></label><label class="wide">Gợi ý trích từ thu nhập (%)<input name="auto_percent" type="number" min="5" max="20" value="${g?.auto_percent||10}" required></label></div><p class="form-hint">Khi thêm thu nhập mới, bạn có thể xác nhận số tiền muốn trích vào hũ. Không chuyển tiền ngân hàng tự động.</p>`,(p,f,key)=>api('/goals'+(g?'/'+g.id:''),{method:g?'PATCH':'POST',body:p,key}));}
function transferModal(id,direction){const g=state.goals.find(x=>x.id===id);formModal(direction==='deposit'?'Nạp vào hũ tiết kiệm':'Rút tiền khỏi hũ',`<div class="notice info">${esc(g.name)} · Đã tích lũy ${money(g.saved)}</div><label>${direction==='deposit'?'Lấy từ ví':'Chuyển về ví'}<select name="wallet_id">${options(state.wallets,null)}</select></label><label>Số tiền (VND)<input name="amount" type="number" min="1" max="1000000000000" required></label>`,(p,f,key)=>api('/goals/'+id+'/transfer',{method:'POST',body:{...p,direction},key}));}
function categoryModal(c=null){formModal(c?'Sửa danh mục':'Thêm danh mục',`<label>Tên danh mục<input name="name" required maxlength="80" value="${esc(c?.name||'')}"></label><div class="form-grid"><label>Loại<select name="type"><option value="expense">Chi tiêu</option><option value="income" ${c?.type==='income'?'selected':''}>Thu nhập</option></select></label><label>Biểu tượng (emoji)<input name="icon" maxlength="16" required value="${esc(c?.icon||'🏷️')}"></label></div>`,(p,f,key)=>api('/categories'+(c?'/'+c.id:''),{method:c?'PATCH':'POST',body:p,key}));}
function walletModal(w=null){formModal(w?'Đổi tên ví':'Thêm nguồn tiền',`<label>Tên ví<input name="name" maxlength="80" required value="${esc(w?.name||'')}" placeholder="Tiền mặt, ngân hàng, ví điện tử…"></label>${w?'':`<label>Số dư ban đầu (VND)<input name="initial_balance" type="number" min="0" max="1000000000000" value="0" required></label><p class="form-hint">Số dư ban đầu là tiền bạn đang có trước khi dùng ứng dụng, không tính vào báo cáo thu nhập.</p>`}`,(p,f,key)=>api('/wallets'+(w?'/'+w.id:''),{method:w?'PATCH':'POST',body:p,key}));}
function profileModal(){formModal('Cập nhật tài khoản',`<label>Họ và tên<input name="name" maxlength="100" required value="${esc(user.name)}"></label><label>Trường đang học<input name="school" maxlength="150" value="${esc(user.school)}"></label><label>Mã sinh viên<input name="student_id" maxlength="50" value="${esc(user.student_id)}"></label><details><summary>Đổi mật khẩu</summary><p class="form-hint">Để trống hai ô bên dưới nếu giữ mật khẩu hiện tại.</p><label>Mật khẩu hiện tại<input name="current_password" type="password" autocomplete="current-password"></label><label>Mật khẩu mới<input name="new_password" type="password" minlength="8" maxlength="128" autocomplete="new-password"></label></details>`,async(p,f,key)=>{const r=await api('/profile',{method:'PATCH',body:p,key});user=r.user;return r;});}
function groupModal(join=false){formModal(join?'Tham gia quỹ nhóm':'Tạo quỹ nhóm',join?'<label>Mã tham gia<input name="code" maxlength="24" required placeholder="Nhập mã do trưởng nhóm chia sẻ"></label>':'<label>Tên nhóm<input name="name" maxlength="100" required placeholder="Đà Lạt cùng hội bạn, Phòng 302…"></label>',async(p,f,key)=>{const r=await api(join?'/groups/join':'/groups',{method:'POST',body:p,key});groupId=r.id;page='groups';return r;},join?'Tham gia nhóm':'Tạo nhóm');}
function groupEntryModal(prefill=null){
 const g=groupData, isAdmin=g.role==='admin';
 formModal('Ghi giao dịch nhóm',`<div class="form-grid"><label class="wide">Loại giao dịch<select name="kind">${Object.entries(kinds).filter(([k])=>isAdmin||k==='split').map(([v,l])=>`<option value="${v}" ${(prefill?.kind||'split')===v?'selected':''}>${l}</option>`).join('')}</select></label><label>Số tiền (VND)<input name="amount" type="number" required min="1" max="1000000000000" value="${prefill?.amount||''}"></label><label>Ngày thực hiện<input name="date" type="date" required max="${state.today}" value="${state.today}"></label><label>Người nộp / trả tiền<select name="payer_id">${options(g.members.filter(m=>isAdmin||m.id===user.id),prefill?.from||user.id)}</select></label><label id="receiver-label">Người nhận (trả nợ)<select name="receiver_id">${options(g.members,prefill?.to)}</select></label><label class="wide">Nội dung<input name="note" maxlength="500" required value="${prefill?'Thanh toán nợ nhóm':''}" placeholder="Ví dụ: Tiền ăn tối cả nhóm"></label><label class="wide">Mức ưu tiên<select name="priority">${Object.entries(priorities).map(([v,l])=>`<option value="${v}" ${v==='necessary'?'selected':''}>${l}</option>`).join('')}</select></label></div><div id="participants"><p class="form-hint">Chia đều cho các thành viên được chọn. Phần lẻ 1 đồng được phân theo mã thành viên tăng dần.</p>${g.members.map(m=>`<label class="check-label"><input class="participant" type="checkbox" value="${m.id}" checked>${esc(m.name)}</label>`).join('')}</div><div id="group-kind-hint" class="notice info"></div>`,(p,f,key)=>api('/groups/'+g.id+'/entries',{method:'POST',body:{...p,payer_id:Number(p.payer_id),receiver_id:Number(p.receiver_id),participants:$$('.participant:checked',f).map(c=>Number(c.value))},key}),'Lưu giao dịch',form=>{
 const kind=$('[name=kind]',form);const change=()=>{const k=kind.value;$('#receiver-label').hidden=k!=='settlement';$('#participants').hidden=!['split','fund_expense'].includes(k);$('#group-kind-hint').textContent={split:'Người trả ứng tiền cá nhân. Hệ thống ghi nợ phần chia của từng thành viên; số dư quỹ không đổi.',fund_expense:'Trừ tiền có sẵn trong quỹ. Phần chia chỉ dùng để đối chiếu, không phát sinh nợ cá nhân.',contribution:'Khoản đóng góp vào quỹ dùng chung, không phát sinh khoản phải thu hay nợ.',settlement:'Xác nhận tiền đã trả thực tế giữa hai thành viên. Không ảnh hưởng số dư quỹ.'}[k];};kind.addEventListener('change',change);change();
 });
}
function receiptModal(id){formModal('Đính kèm hóa đơn',`<label>Chọn ảnh hoặc PDF<input name="receipt" type="file" accept="image/png,image/jpeg,application/pdf" required></label><p class="form-hint">Tối đa ${state.receipt_max_mb || 5} MB. Chứng từ được lưu trong cơ sở dữ liệu; chỉ thành viên nhóm được tải về. Hóa đơn đã lưu không thể ghi đè.</p>`,(p,f,key)=>api('/groups/'+groupId+'/entries/'+id+'/receipt',{method:'POST',body:new FormData(f),key}),'Lưu hóa đơn');}
function notificationsModal(){modal('Cảnh báo ngân sách',state.warnings.length?state.warnings.map(b=>`<div class="notice ${b.percent>=100?'danger':''}"><b>${esc(b.name)} · ${b.percent}%</b><br>Đã chi ${money(b.spent)} / ${money(b.limit)}<br>${dateVN(b.start)} — ${dateVN(b.end)}</div>`).join(''):empty('Ngân sách đang ổn','Chưa có ngân sách đang hiệu lực chạm ngưỡng cảnh báo.'));}
async function action(name,id){
 const find=(list)=>list.find(x=>x.id===id);
 if(name==='close')return closeModal();
 if(name==='transaction')return transactionModal();
 if(name==='edit-tx')return transactionModal(find(txResult.items));
 if(name==='delete-tx')return confirmAction('Xóa giao dịch?','Số dư và ngân sách sẽ được tính lại. Khoản trích hũ gắn với giao dịch cũng được hoàn lại nếu còn đủ tiền trong hũ.',key=>api('/transactions/'+id,{method:'DELETE',key}));
 if(name==='budget'||name==='edit-budget')return budgetModal(id?find(state.budgets):null);
 if(name==='goal'||name==='edit-goal')return goalModal(id?find(state.goals):null);
 if(name==='delete-budget')return confirmAction('Xóa ngân sách?','Giao dịch thu chi vẫn được giữ lại.',key=>api('/budgets/'+id,{method:'DELETE',key}));
 if(name==='delete-goal')return confirmAction('Xóa hũ tiết kiệm?','Chỉ xóa được hũ có số tiền bằng 0. Hãy rút tiền về ví trước.',key=>api('/goals/'+id,{method:'DELETE',key}));
 if(name==='deposit'||name==='withdraw')return transferModal(id,name);
 if(name==='goal-history'){const r=await api('/goals/'+id+'/history');return modal('Lịch sử hũ tiết kiệm',r.items.length?`<div class="settings-list">${r.items.map(e=>`<div class="settings-row"><div>${e.amount>0?'Nạp vào hũ':'Rút về ví'} · ${esc(e.wallet)}<small>${timeVN(e.time)} · ${e.automatic?'Trích từ thu nhập':'Chuyển thủ công'}</small></div><b class="${e.amount>0?'positive':'negative'}">${money(e.amount)}</b></div>`).join('')}</div><p class="form-hint">100 khoản chuyển gần nhất.</p>`:empty('Chưa có lần chuyển tiền','Nạp vào hũ để bắt đầu tích lũy.'));}
 if(name==='wallet'||name==='edit-wallet')return walletModal(id?find(state.wallets):null);
 if(name==='delete-wallet')return confirmAction('Xóa ví?','Chỉ có thể xóa ví trống chưa từng có giao dịch. Cần giữ ít nhất một ví.',key=>api('/wallets/'+id,{method:'DELETE',key}));
 if(name==='category'||name==='edit-category')return categoryModal(id?find(state.categories):null);
 if(name==='delete-category')return confirmAction('Xóa danh mục?','Danh mục đang có giao dịch hoặc ngân sách không thể xóa.',key=>api('/categories/'+id,{method:'DELETE',key}));
 if(name==='profile')return profileModal();
 if(name==='logout'){await api('/logout',{method:'POST'});closeModal();await showAuth();return;}
 if(name==='prev-page'||name==='next-page'){txPage+=name==='prev-page'?-1:1;return render();}
 if(name==='tx-all'){txFilters={};txPage=1;return render();}
 if(name==='report-all'){reportFilters={period:'month'};return render();}
 if(name.startsWith('report-')){
  const type=name.slice(7), d=new Date(state.today+'T12:00:00'), asISO=x=>[x.getFullYear(),String(x.getMonth()+1).padStart(2,'0'),String(x.getDate()).padStart(2,'0')].join('-');
  if(type==='today')reportFilters={start:state.today,end:state.today,period:'day'};
  else if(type==='week'){d.setDate(d.getDate()-((d.getDay()+6)%7));const start=asISO(d);d.setDate(d.getDate()+6);reportFilters={start,end:asISO(d),period:'day'};}
  else if(type==='month')reportFilters={...periodBounds(),period:'day'};
  else if(type==='year'){const y=$('#month').value.slice(0,4);reportFilters={start:y+'-01-01',end:y+'-12-31',period:'month'};}
  return render();
 }
 if(name==='group')return groupModal();
 if(name==='join-group')return groupModal(true);
 if(name==='open-group'){groupId=id;groupFilters={kind:'',priority:'',payer:'',sort:'latest'};page='groups';return render();}
 if(name==='back-groups'){groupId=null;groupData=null;return render();}
 if(name==='refresh-group')return render();
 if(name==='copy-code'){try{await navigator.clipboard.writeText(groupData.code);toast('Đã sao chép mã nhóm.');}catch{toast('Mã tham gia: '+groupData.code);}return;}
 if(name==='rotate-code')return confirmAction('Đổi mã tham gia?','Mã hiện tại sẽ hết hiệu lực. Thành viên đang có vẫn ở trong nhóm.',key=>api('/groups/'+groupId+'/code',{method:'POST',key}));
 if(name==='group-entry')return groupEntryModal();
 if(name==='settle'){const s=groupData.settlements[id];return groupEntryModal({...s,kind:'settlement'});}
 if(name==='receipt')return receiptModal(id);
 if(name==='void-entry')return formModal('Hủy giao dịch nhóm',`<div class="notice">Số dư và nợ được tính lại. Giao dịch gốc vẫn được giữ trong sao kê và lịch sử.</div><label>Lý do hủy<input name="reason" maxlength="300" required></label>`,(p,f,key)=>api('/groups/'+groupId+'/entries/'+id+'/void',{method:'POST',body:p,key}),'Xác nhận hủy');
}
document.addEventListener('click',e=>{
 const nav=e.target.closest('[data-nav]');if(nav){navigate(nav.dataset.nav).catch(error=>toast(error.message,'error'));return;}
 const button=e.target.closest('[data-action]');if(button&&!button.disabled)action(button.dataset.action,button.dataset.id==null?null:Number(button.dataset.id)).catch(error=>toast(error.message,'error'));
});
function setAuthMode(mode){authMode=mode;$('#name-field').hidden=mode!=='register';$('[name=name]',$('#auth-form')).required=mode==='register';$('#login-tab').classList.toggle('selected',mode==='login');$('#register-tab').classList.toggle('selected',mode==='register');$('#auth-title').textContent=mode==='login'?'Mừng bạn trở lại!':'Chào chiếc ví mới của bạn!';$('#auth-subtitle').textContent=mode==='login'?'Đăng nhập để tiếp tục chăm sóc chiếc ví của mình.':'Tạo tài khoản và bắt đầu hành trình quản lý tiền.';$('#auth-submit').textContent=mode==='login'?'Đăng nhập →':'Tạo tài khoản →';$('[name=password]',$('#auth-form')).autocomplete=mode==='login'?'current-password':'new-password';$('#auth-error').textContent='';}
$('#login-tab').addEventListener('click',()=>setAuthMode('login'));$('#register-tab').addEventListener('click',()=>setAuthMode('register'));
$('#auth-form').addEventListener('submit',async e=>{
 e.preventDefault();const button=$('#auth-submit');button.disabled=true;$('#auth-error').textContent='';
 try{const p=Object.fromEntries(new FormData(e.target));const r=await api('/'+authMode,{method:'POST',body:p});user=r.user;csrf=r.csrf;e.target.reset();page='dashboard';groupId=null;groupData=null;txFilters={};reportFilters={};await startApp();}
 catch(error){$('#auth-error').textContent=error.message;}finally{button.disabled=false;}
});
$('#modal-close').addEventListener('click',closeModal);
$('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeModal();}});
$('#add-transaction').addEventListener('click',()=>transactionModal());
$('#notification-button').addEventListener('click',notificationsModal);
$('#menu-button').addEventListener('click',()=>$('#sidebar').classList.toggle('open'));
$('#month').addEventListener('change',()=>{if(!$('#month').value)return;txFilters=periodBounds();reportFilters={...periodBounds(),period:'day'};txPage=1;refresh().catch(e=>toast(e.message,'error'));});
$('#quick-search').addEventListener('submit',e=>{e.preventDefault();txFilters={q:new FormData(e.target).get('q')};txPage=1;navigate('transactions').catch(error=>toast(error.message,'error'));});
$('#help-button').addEventListener('click',()=>modal('Bắt đầu cùng Ví Uni',`<ol class="help-list"><li>Thêm thu nhập hoặc tạo ví với số dư ban đầu tại <b>Cài đặt</b>.</li><li>Chọn <b>Thêm giao dịch</b> để ghi thu/chi. Dùng bộ lọc ngày và danh mục để tra cứu.</li><li>Đặt ngân sách ngày, tuần hoặc tháng. Cảnh báo hiển thị trong ứng dụng khi chi đạt ngưỡng.</li><li>Tạo hũ tiết kiệm, nạp tiền từ ví hoặc xác nhận đề xuất trích lập khi thêm thu nhập.</li><li>Tạo quỹ nhóm và chia sẻ mã. Phân biệt <b>chi quỹ</b> với <b>ứng tiền cá nhân</b> để số dư chính xác.</li><li>Đăng xuất và đăng nhập lại bằng cùng tài khoản để tiếp tục với dữ liệu đã lưu.</li></ol>`));
async function startApp(){await refresh();$('#auth').hidden=true;$('#app').hidden=false;$('#loading').hidden=true;}
async function boot(){
 const parts=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit'}).formatToParts(new Date());
 $('#month').value=parts.find(p=>p.type==='year').value+'-'+parts.find(p=>p.type==='month').value;
 try{const r=await api('/auth');csrf=r.csrf;user=r.user;if(user)await startApp();else await showAuth();}
 catch(error){$('#loading').textContent='Không kết nối được cơ sở dữ liệu. Kiểm tra cấu hình và khởi động lại máy chủ.';toast(error.message,'error');}
}
setInterval(()=>{if(user&&page==='groups'&&groupId&&!document.hidden&&!$('#modal').open&&!document.activeElement?.closest('#group-filters'))render().catch(e=>toast(e.message,'error'));},15000);
boot();
