const api = require('../../utils/api')
const empty = { name:'', company:'', role:'', interests:'', score:50 }
Page({
  data:{ contacts:[], filtered:[], showForm:false, editingId:null, form:{...empty} },
  onShow(){ this.load(); const card=wx.getStorageSync('pendingCard'); if(card){wx.removeStorageSync('pendingCard');this.setData({showForm:true,editingId:null,form:card})} },
  async load(){ try{const rows=await api.get('/contacts');const mapped=rows.map(x=>({...x,interestList:x.interests?x.interests.split(','):[]}));this.setData({contacts:mapped,filtered:mapped})}catch(e){wx.showToast({title:e.message,icon:'none'})} },
  search(e){const q=e.detail.value.toLowerCase();this.setData({filtered:this.data.contacts.filter(x=>(x.name+x.company+x.interests).toLowerCase().includes(q))})},
  openCreate(){this.setData({showForm:true,editingId:null,form:{...empty}})}, close(){this.setData({showForm:false})}, field(e){this.setData({['form.'+e.currentTarget.dataset.key]:e.detail.value})},
  edit(e){const x=this.data.contacts.find(v=>v.id===e.currentTarget.dataset.id);this.setData({showForm:true,editingId:x.id,form:{name:x.name,company:x.company,role:x.role,interests:x.interests,score:x.score}})},
  async save(){const f=this.data.form;if(!f.name.trim()||!f.company.trim())return wx.showToast({title:'Name and company required',icon:'none'});const body={name:f.name.trim(),company:f.company.trim(),role:f.role.trim(),interests:f.interests.split(',').map(x=>x.trim()).filter(Boolean),score:Number(f.score)};try{if(this.data.editingId)await api.patch('/contacts/'+this.data.editingId,body);else await api.post('/contacts',body);this.setData({showForm:false});await this.load();wx.showToast({title:'Saved'})}catch(e){wx.showToast({title:e.message,icon:'none'})}},
  remove(e){const id=e.currentTarget.dataset.id;wx.showModal({title:'Delete contact',content:'Contact and conversations will be permanently deleted.',success:async r=>{if(r.confirm){try{await api.del('/contacts/'+id);await this.load()}catch(error){wx.showToast({title:error.message,icon:'none'})}}}})}
})
