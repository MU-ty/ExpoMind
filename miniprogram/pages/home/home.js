const api = require('../../utils/api')

Page({
  data: {stats: {contacts: 0, high_intent: 0, conversations: 0}, contacts: [], isAdmin: false},

  onShow() {
    const tabBar = typeof this.getTabBar === 'function' && this.getTabBar()
    if (tabBar) tabBar.setData({selected: 0})
    this.load()
  },

  async load() {
    try {
      const [stats, contacts, user] = await Promise.all([api.get('/dashboard'), api.get('/contacts'), api.get('/auth/me')])
      const recentContacts = await Promise.all(contacts.slice(0, 5).map(async contact => ({
        ...contact,
        initials: contact.name.split(/\s+/).map(value => value[0]).join('').slice(0, 2).toUpperCase(),
        photoUrl: await api.imagePath(contact.photo_url)
      })))
      this.setData({stats, contacts: recentContacts, isAdmin: user.role === 'admin'})
    } catch (error) {
      wx.showToast({title: error.message, icon: 'none'})
    }
  },

  goCapture() {
    wx.switchTab({url: '/pages/capture/capture'})
  },

  goAdmin() {
    wx.navigateTo({url: '/pages/admin/admin'})
  }
})
