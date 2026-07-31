const api = require('./utils/api')
App({
  globalData: { user: null },
  onLaunch() {
    const token = wx.getStorageSync('token')
    if (token) api.get('/auth/me').then(user => { this.globalData.user = user }).catch(() => wx.removeStorageSync('token'))
  }
})
