function addCatalogForm(target, type) {
  const host=document.getElementById(target);if(!host)return;
  const form=document.createElement('form');form.className='card';
  const label=document.createElement('label');label.className='field';label.textContent=type==='rooms'?'新增会议室名称':'新增车牌';
  const input=document.createElement('input');input.required=true;label.append(input);form.append(label);
  let capacity;
  if(type==='rooms'){
    const l=document.createElement('label');l.className='field';l.textContent='容量';capacity=document.createElement('input');
    capacity.type='number';capacity.min='1';capacity.max='1000';capacity.value='10';l.append(capacity);form.append(l);
  }
  const submit=document.createElement('button');submit.className='btn';submit.textContent='新增';form.append(submit);
  const message=document.createElement('p');message.setAttribute('role','status');form.append(message);
  form.onsubmit=async e=>{
    e.preventDefault();submit.disabled=true;
    try{
      const value=type==='vehicles'?input.value.replace(/\s/g,'').toUpperCase():input.value.trim();
      const existing=type==='rooms'?state.rooms:state.vehicles;
      if(existing.some(x=>(x.name||x.plate)===value))throw new Error('资源已存在，请在列表中维护');
      const result=await api('/admin/'+type+'/'+encodeURIComponent(value),'PUT',type==='rooms'?{capacity:Number(capacity.value),enabled:true}:{enabled:true});
      message.textContent=result.cacheInvalidated?'已新增':'已新增，缓存暂不可用；目录将回源读取';
      input.value='';await (type==='rooms'?loadRooms():loadVehicles());
    }catch(error){message.textContent=error.message;}finally{submit.disabled=false;}
  };
  host.prepend(form);
}
addCatalogForm('panel-rooms','rooms');addCatalogForm('panel-vehicles','vehicles');
