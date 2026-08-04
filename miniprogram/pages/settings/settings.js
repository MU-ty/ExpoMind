const api = require('../../utils/api')
const config = require('../../config')

Page({
  data: {
    loading: true,
    saving: false,
    user: null,
    initial: 'E',
    name: '',
    eventName: '',
    apiBaseUrl: config.getApiBaseUrl()
  },

  onShow() {
    const tabBar = typeof this.getTabBar === 'function' && this.getTabBar()
    if (tabBar) tabBar.setData({selected: 4, hidden: false})
    if (!wx.getStorageSync('token')) {
      wx.reLaunch({url: '/pages/login/login'})
      return
    }
    this.setData({apiBaseUrl: config.getApiBaseUrl()})
    this.loadProfile()
  },

  async loadProfile() {
    this.setData({loading: true})
    try {
      const user = await api.get('/auth/me')
      getApp().globalData.user = user
      this.setData({
        user,
        initial: (user.name || 'E').charAt(0).toUpperCase(),
        name: user.name || '',
        eventName: user.event_name || ''
      })
    } catch (error) {
      wx.showToast({title: error.message, icon: 'none'})
    } finally {
      this.setData({loading: false})
    }
  },

  field(event) {
    this.setData({[event.currentTarget.dataset.key]: event.detail.value})
  },

  async saveProfile() {
    const name = this.data.name.trim()
    const eventName = this.data.eventName.trim()
    if (name.length < 2) return wx.showToast({title: '姓名至少需要 2 个字符', icon: 'none'})
    if (eventName.length < 2) return wx.showToast({title: '展会名称至少需要 2 个字符', icon: 'none'})

    this.setData({saving: true})
    try {
      const user = await api.patch('/auth/me', {name, event_name: eventName})
      getApp().globalData.user = user
      this.setData({user, initial: user.name.charAt(0).toUpperCase(), name: user.name, eventName: user.event_name})
      wx.showToast({title: '个人资料已保存'})
    } catch (error) {
      wx.showModal({title: '保存失败', content: error.message, showCancel: false})
    } finally {
      this.setData({saving: false})
    }
  },

  logout() {
    wx.showModal({
      title: '退出登录',
      content: '确定要退出当前账号吗？',
      confirmText: '退出',
      confirmColor: '#963d42',
      success: result => {
        if (!result.confirm) return
        wx.removeStorageSync('token')
        getApp().globalData.user = null
        wx.reLaunch({url: '/pages/login/login'})
      }
    })
  }
})
