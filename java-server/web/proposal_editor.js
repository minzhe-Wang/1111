// Each card captures its own ID/version. A later chat cannot retarget an old confirm button.
async function loadDrafts() {
  const drafts=await api('/agent/proposals');
  for(const draft of drafts) renderProposal(draft);
}
async function showProposal(id) { renderProposal(await api('/agent/proposals/'+encodeURIComponent(id))); }
function renderProposal(draft) {
  document.querySelectorAll('.proposal').forEach(x=>{if(x.dataset.id===draft.id)x.remove();});
  const card=document.createElement('div'); card.className='proposal'; card.dataset.id=draft.id;
  const title=document.createElement('h4');
  title.textContent=`${KIND[draft.payload.kind]}草稿 · 有效至 ${new Date(draft.expires).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}（北京时间）`;
  card.append(title);
  let version=draft.version;
  const form=document.createElement('form'), data={...draft.payload};
  const fields=[['title','标题'],['start','开始时间（北京时间）'],['end','结束时间（北京时间）'],
    ['detail',data.kind==='room'?'会议室':'备注'],['destination','目的地'],['vehicle','车牌'],
    ['passengers','参会人数'],['leave_type','假别'],['amount','申报金额（元）'],['category','类别']];
  const controls={};
  for(const [key,label] of fields) {
    if (['start','end'].includes(key)&&data.kind==='expense') continue;
    if(key==='destination'&&!['travel','vehicle'].includes(data.kind))continue;
    if(key==='vehicle'&&data.kind!=='vehicle')continue;
    if(key==='passengers'&&data.kind!=='room')continue;
    if(key==='leave_type'&&data.kind!=='leave')continue;
    if(['amount','category'].includes(key)&&data.kind!=='expense')continue;
    const wrap=document.createElement('label');wrap.className='field';wrap.textContent=label;
    let options=null;
    if(key==='leave_type') options=['事假','病假','年假','调休'];
    if(key==='category') options=['交通','餐饮','办公','住宿','其他'];
    if(key==='vehicle') options=state.vehicles.map(x=>x.name);
    if(key==='detail'&&data.kind==='room') options=state.rooms.map(x=>x.name);
    const input=document.createElement(options?'select':'input');
    if(options) { input.add(new Option('请选择','')); for(const x of options) input.add(new Option(x,x)); }
    else input.type=['start','end'].includes(key)?'datetime-local':key==='amount'||key==='passengers'?'number':'text';
    if(key==='amount') {input.min='0.01'; input.max='50000'; input.step='0.01';}
    if(key==='passengers') {input.min='1';input.max='1000';input.step='1';}
    input.value=['start','end'].includes(key)?(data[key]||'').slice(0,16):(data[key]??'');
    controls[key]=input;wrap.append(input);form.append(wrap);
  }
  const note=document.createElement('p');note.textContent=`票据 ${(data.receipts||[]).length} 张；核对并保存修改后，再确认提交。`;
  let receiptInput;
  if(data.kind==='expense'){
    const label=document.createElement('label');label.className='field';label.textContent='替换票据（一次选择1至3张；不选择则保留原票据）';
    receiptInput=document.createElement('input');receiptInput.type='file';receiptInput.multiple=true;receiptInput.accept='image/png,image/jpeg,image/webp';
    label.append(receiptInput);form.append(label);
  }
  const status=document.createElement('p');status.setAttribute('role','status');
  const actions=document.createElement('div');actions.className='actions';
  const save=button('保存修改',async()=>{
    try {
      const payload={...data};
      for(const [key,input] of Object.entries(controls)) payload[key]=key==='passengers'?Number(input.value):input.value;
      if(receiptInput?.files.length){
        const chosen=[...receiptInput.files];
        if(chosen.length>3||chosen.some(f=>f.size>2*1024*1024))throw new Error('请选择1至3张票据，每张不超过2MB');
        payload.receipts=await Promise.all(chosen.map(fileToData));
      }
      const result=await api('/agent/proposals/'+draft.id,'PUT',{version,entry:payload});
      Object.assign(data,result.payload); version=result.version; confirm.disabled=false;
      note.textContent=`票据 ${(data.receipts||[]).length} 张；请核对申报金额后确认。`;
      status.textContent='修改已保存，请核对当前内容后确认。';
    } catch(e){status.textContent=e.message;}
  },'ghost');
  const confirm=button('确认提交',async()=>{
    confirm.disabled=true;
    try {
      const result=await api('/agent/confirm/'+draft.id,'POST',{version});
      card.remove();addBubble('已保存，记录编号 '+result.id,false);
      if(result.warnings?.length)alert(result.warnings.join('\n'));
      await loadRecords();
    } catch(e){status.textContent=e.message;confirm.disabled=false;}
  });
  form.oninput=()=>{confirm.disabled=true;status.textContent='内容已修改，请先保存并核对。';};
  form.onsubmit=e=>e.preventDefault();
  const cancel=button('取消草稿',async()=>{
    try{await api('/agent/proposals/'+draft.id,'DELETE');card.remove();}catch(e){status.textContent=e.message;}
  },'danger');
  const regenerate=button('过期后重新生成',async()=>{
    try{const result=await api('/agent/proposals/'+draft.id+'/regenerate','POST');card.remove();renderProposal(result);}
    catch(e){status.textContent=e.message;}
  },'ghost');
  actions.append(save,confirm,cancel,regenerate);form.append(note,actions,status);card.append(form);$('chatLog').append(card);
}
// Explicitly abandon the previous submission identity only after checking its result.
const fresh=button('开始新申请',()=>{
  if(state.submission&&!confirm('上次提交结果可能尚未返回，请先刷新记录核对。确认开始新的申请？'))return;
  state.submission=null; toast('已开始新申请，现有填写内容保留');
},'ghost');
$('entryForm').append(fresh);
