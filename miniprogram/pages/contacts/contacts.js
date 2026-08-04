const api = require('../../utils/api')
const empty = {name: '', company: '', role: '', phone: '', contactEmail: '', interests: '', summary: '', gender: 'unspecified', score: 50}

Page({
  data: {contacts: [], filtered: [], showForm: false, editingId: null, form: {...empty}, genderLabels: ['未指定', '男', '女'], genderIndex: 0},

  onShow() {
    const tabBar = typeof this.getTabBar === 'function' && this.getTabBar()
    if (tabBar) tabBar.setData({selected: 1, hidden: false})
    this.load()
    const card = wx.getStorageSync('pendingCard')
    if (card) {
      wx.removeStorageSync('pendingCard')
      this.setData({showForm: true, editingId: null, form: {...empty, ...card}, genderIndex: 0})
      this.setTabBarHidden(true)
    }
  },

  setTabBarHidden(hidden) {
    const tabBar = typeof this.getTabBar === 'function' && this.getTabBar()
    if (tabBar) tabBar.setData({hidden})
  },

  async load() {
    try {
      const rows = await api.get('/contacts')
      const mapped = await Promise.all(rows.map(async item => ({
        ...item,
        interestList: item.interests ? item.interests.split(',') : [],
        photoUrl: await api.imagePath(item.photo_url),
        initial: item.name.slice(0, 1)
      })))
      this.setData({contacts: mapped, filtered: mapped})
    } catch (error) {
      wx.showToast({title: error.message, icon: 'none'})
    }
  },

  search(event) {
    const query = event.detail.value.toLowerCase()
    this.setData({filtered: this.data.contacts.filter(item => `${item.name}${item.company}${item.interests}`.toLowerCase().includes(query))})
  },

  openCreate() {
    this.setData({showForm: true, editingId: null, form: {...empty}, genderIndex: 0})
    this.setTabBarHidden(true)
  },

  close() {
    this.setData({showForm: false})
    this.setTabBarHidden(false)
  },

  field(event) {
    this.setData({[`form.${event.currentTarget.dataset.key}`]: event.detail.value})
  },

  genderChange(event) {
    const genderIndex = Number(event.detail.value)
    this.setData({'form.gender': ['unspecified', 'male', 'female'][genderIndex], genderIndex})
  },

  edit(event) {
    const contact = this.data.contacts.find(item => item.id === event.currentTarget.dataset.id)
    if (!contact) return
    this.setData({
      showForm: true,
      editingId: contact.id,
      genderIndex: contact.gender === 'male' ? 1 : contact.gender === 'female' ? 2 : 0,
      form: {
        name: contact.name,
        company: contact.company,
        role: contact.role,
        phone: contact.phone || '',
        contactEmail: contact.contact_email || '',
        interests: contact.interests,
        summary: contact.summary || '',
        gender: contact.gender || 'unspecified',
        score: contact.score
      }
    })
    this.setTabBarHidden(true)
  },

  async save() {
    const form = this.data.form
    if (!form.name.trim() || !form.company.trim()) return wx.showToast({title: '请填写姓名和公司', icon: 'none'})
    const body = {
      name: form.name.trim(),
      company: form.company.trim(),
      role: form.role.trim(),
      phone: form.phone.trim(),
      contact_email: form.contactEmail.trim(),
      interests: form.interests.split(/[,，]/).map(item => item.trim()).filter(Boolean),
      summary: form.summary.trim(),
      gender: form.gender,
      score: Math.max(0, Math.min(100, Number(form.score) || 0))
    }
    try {
      if (this.data.editingId) await api.patch(`/contacts/${this.data.editingId}`, body)
      else await api.post('/contacts', body)
      this.setData({showForm: false})
      this.setTabBarHidden(false)
      await this.load()
      wx.showToast({title: '已保存'})
    } catch (error) {
      wx.showToast({title: error.message, icon: 'none'})
    }
  },

  remove(event) {
    const id = event.currentTarget.dataset.id
    wx.showModal({
      title: '删除联系人',
      content: '该联系人及其交流记录将被永久删除。',
      success: async result => {
        if (!result.confirm) return
        try {
          await api.del(`/contacts/${id}`)
          await this.load()
        } catch (error) {
          wx.showToast({title: error.message, icon: 'none'})
        }
      }
    })
  }
})
