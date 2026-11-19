function recordStatus(row) {
  const names = {active:'已登记',pending:'待审批',approved:'已通过',rejected:'已驳回',cancelled:'已撤回/取消',archived:'已归档'};
  if (row.status === 'archived') return '已归档 · ' + ({approved:'通过',rejected:'驳回'}[row.data.approval_result] || '历史审批结果待核实');
  return names[row.status] || row.status;
}
function appendHistory(container, row) {
  for (const warning of row.warnings || []) {
    const p = document.createElement('p'); p.className='remark'; p.textContent=warning; container.append(p);
  }
  if (!row.data.history?.length) return;
  const details=document.createElement('details'), summary=document.createElement('summary');
  summary.textContent='操作历史'; details.append(summary);
  for (const h of row.data.history) {
    const p=document.createElement('p');
    p.textContent=`${h.time} · ${h.actor} · ${h.action} · ${h.reason || ''}`;
    details.append(p);
    if (h.before) {
      const before=document.createElement('p');
      before.textContent=`修改前：${h.before.title || ''} ${h.before.start || ''} 至 ${h.before.end || ''} ${h.before.detail || ''}`;
      details.append(before);
    }
  }
  container.append(details);
}
