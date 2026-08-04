const api = require('../../utils/api')
const config = require('../../config')

Page({
  data: {
    loading: false,
    passwordLoading: false,
    wechatConfigured: null,
    localDev: config.isLocalDevelopment(),
    apiBaseUrl: config.getApiBaseUrl(),
    endpointDraft: config.getApiBaseUrl(),
    email: 'admin@your-company.com',
    password: ''
  },

  onLoad() {
    this.checkWechatStatus()
  },

  onShow() {
    if (wx.getStorageSync('token')) wx.switchTab({url: '/pages/home/home'})
  },

  async checkWechatStatus() {
    try {
      const status = await api.get('/auth/wechat/status')
      this.setData({wechatConfigured: Boolean(status.configured)})
    } catch (error) {
      this.setData({wechatConfigured: false})
      wx.showToast({title: error.message, icon: 'none'})
    }
  },

  field(event) {
    this.setData({[event.currentTarget.dataset.key]: event.detail.value})
  },

  async saveEndpoint() {
    let endpoint = this.data.endpointDraft.trim().replace(/\/$/, '')
    if (!/^https?:\/\/[^\s]+$/i.test(endpoint)) {
      return wx.showToast({title: '请输入完整的 HTTP 或 HTTPS 地址', icon: 'none'})
    }
    if (!/\/api$/i.test(endpoint)) endpoint += '/api'
    wx.setStorageSync('apiBaseUrl', endpoint)
    this.setData({apiBaseUrl: endpoint, endpointDraft: endpoint, wechatConfigured: null})
    wx.showLoading({title: '正在测试连接'})
    try {
      const health = await api.get('/health')
      if (health.status !== 'ok') throw new Error('健康检查返回异常')
      wx.showToast({title: '接口连接成功'})
      await this.checkWechatStatus()
    } catch (error) {
      this.setData({wechatConfigured: false})
      wx.showModal({title: '接口连接失败', content: `${error.message}\n\n请确认手机与电脑处于同一 Wi-Fi，且电脑地址和端口正确。`, showCancel: false})
    } finally {
      wx.hideLoading()
    }
  },

  finishLogin(result) {
    wx.setStorageSync('token', result.access_token)
    getApp().globalData.user = result.user
    wx.switchTab({url: '/pages/home/home'})
  },

  loginWechat() {
    if (!this.data.wechatConfigured) {
      return wx.showToast({title: '服务端尚未配置微信登录', icon: 'none'})
    }
    this.setData({loading: true})
    wx.login({
      success: async ({code}) => {
        try {
          const result = await api.post('/auth/wechat', {code, display_name: '微信用户'})
          this.finishLogin(result)
        } catch (error) {
          wx.showModal({title: '登录失败', content: error.message, showCancel: false})
        } finally {
          this.setData({loading: false})
        }
      },
      fail: () => {
        this.setData({loading: false})
        wx.showToast({title: '无法获取微信登录凭证', icon: 'none'})
      }
    })
  },

  async loginPassword() {
    const email = this.data.email.trim()
    if (!email || !this.data.password) {
      return wx.showToast({title: '请输入邮箱和密码', icon: 'none'})
    }
    this.setData({passwordLoading: true})
    try {
      const result = await api.post('/auth/login', {email, password: this.data.password})
      this.finishLogin(result)
    } catch (error) {
      wx.showModal({title: '登录失败', content: error.message, showCancel: false})
    } finally {
      this.setData({passwordLoading: false})
    }
  }
})
