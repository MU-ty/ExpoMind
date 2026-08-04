const api = require('../../utils/api')
const recorder = wx.getRecorderManager()

Page({
  data: {
    cameraOn: false,
    cameraPosition: 'back',
    consented: false,
    contacts: [],
    contactNames: [],
    contactIndex: 0,
    selectedContact: null,
    transcript: '',
    analysis: null,
    nextAction: '',
    analyzing: false,
    recording: false,
    transcribing: false,
    recordSeconds: 0,
    referencePhotoUrl: ''
  },

  onLoad() {
    this.handleRecorderStop = result => this.transcribeRecording(result.tempFilePath)
    this.handleRecorderError = error => {
      this.stopRecordTimer()
      this.setData({recording: false, transcribing: false})
      wx.showModal({title: '录音失败', content: error.errMsg || '无法使用麦克风', showCancel: false})
    }
    recorder.onStop(this.handleRecorderStop)
    recorder.onError(this.handleRecorderError)
  },

  onShow() {
    const tabBar = typeof this.getTabBar === 'function' && this.getTabBar()
    if (tabBar) tabBar.setData({selected: 2, hidden: false})
    this.loadContacts()
  },

  setTabBarHidden(hidden) {
    const tabBar = typeof this.getTabBar === 'function' && this.getTabBar()
    if (tabBar) tabBar.setData({hidden})
  },

  onUnload() {
    this.stopRecordTimer()
    if (this.data.recording) recorder.stop()
    if (recorder.offStop) recorder.offStop(this.handleRecorderStop)
    if (recorder.offError) recorder.offError(this.handleRecorderError)
  },

  async loadContacts() {
    try {
      const contacts = await api.get('/contacts')
      const selected = this.data.selectedContact
      const selectedContact = selected ? contacts.find(item => item.id === selected.id) || null : null
      const selectedIndex = selectedContact ? contacts.findIndex(item => item.id === selectedContact.id) + 1 : 0
      this.setData({
        contacts,
        contactNames: ['请选择已核实联系人', ...contacts.map(item => `${item.name} · ${item.company}`)],
        contactIndex: selectedIndex,
        selectedContact,
        referencePhotoUrl: ''
      })
      if (selectedContact && selectedContact.photo_url) this.loadReferencePhoto(selectedContact)
    } catch (error) {
      wx.showToast({title: error.message, icon: 'none'})
    }
  },

  consentChange(event) {
    const consented = event.detail.value
    if (!consented && this.data.recording) recorder.stop()
    this.setData({consented})
  },

  openCamera() {
    if (!this.data.consented) {
      return wx.showModal({title: '需要明确同意', content: '请先确认已获得对方对拍摄和记录的明确同意。', showCancel: false})
    }
    this.setData({cameraOn: true})
  },

  cameraError(error) {
    this.setData({cameraOn: false})
    wx.showToast({title: error.detail && error.detail.errMsg || '摄像头不可用', icon: 'none'})
  },

  switchCamera() {
    this.setData({cameraPosition: this.data.cameraPosition === 'back' ? 'front' : 'back'})
  },

  selectContact(event) {
    const index = Number(event.detail.value)
    const selectedContact = index > 0 ? this.data.contacts[index - 1] : null
    this.setData({
      contactIndex: index,
      selectedContact,
      referencePhotoUrl: ''
    })
    if (selectedContact && selectedContact.photo_url) this.loadReferencePhoto(selectedContact)
    this.setTabBarHidden(false)
  },

  async loadReferencePhoto(contact) {
    const localPath = await api.imagePath(contact.photo_url)
    if (this.data.selectedContact && this.data.selectedContact.id === contact.id) {
      this.setData({referencePhotoUrl: localPath})
    }
  },

  contactPickerOpen() {
    this.setTabBarHidden(true)
  },

  contactPickerCancel() {
    this.setTabBarHidden(false)
  },

  goContacts() {
    wx.switchTab({url: '/pages/contacts/contacts'})
  },

  transcriptInput(event) {
    this.setData({transcript: event.detail.value, analysis: null})
  },

  nextInput(event) {
    this.setData({nextAction: event.detail.value})
  },

  capture() {
    return new Promise((resolve, reject) => wx.createCameraContext().takePhoto({
      quality: 'high',
      success: result => resolve(result.tempImagePath),
      fail: reject
    }))
  },

  async scanCard() {
    if (!this.data.consented || !this.data.cameraOn) {
      return wx.showToast({title: '请先确认同意并开启摄像头', icon: 'none'})
    }
    wx.showLoading({title: '正在识别名片'})
    try {
      const path = await this.capture()
      const data = await api.upload('/ai/business-card', path, 'image')
      const result = data.result || {}
      wx.setStorageSync('pendingCard', {
        name: result.name || '',
        company: result.company || '',
        role: result.role || '',
        phone: result.phone || '',
        contactEmail: result.email || '',
        interests: Array.isArray(result.interests) ? result.interests.join(', ') : '',
        summary: '',
        gender: 'unspecified',
        score: 50
      })
      wx.switchTab({url: '/pages/contacts/contacts'})
    } catch (error) {
      wx.showModal({title: '名片识别失败', content: error.message, showCancel: false})
    } finally {
      wx.hideLoading()
    }
  },

  async takeReference() {
    if (!this.data.consented || !this.data.cameraOn) {
      return wx.showToast({title: '请先确认同意并开启摄像头', icon: 'none'})
    }
    if (!this.data.selectedContact) {
      return wx.showToast({title: '请先选择联系人', icon: 'none'})
    }
    wx.showLoading({title: '正在保存照片'})
    try {
      const path = await this.capture()
      const result = await api.upload(`/contacts/${this.data.selectedContact.id}/photo`, path, 'image')
      const selectedContact = {...this.data.selectedContact, photo_url: result.photo_url}
      this.setData({referencePhotoUrl: path, selectedContact})
      const contacts = this.data.contacts.map(item => item.id === selectedContact.id ? selectedContact : item)
      this.setData({contacts})
      wx.showToast({title: '照片已保存'})
    } catch (error) {
      wx.showModal({title: '照片保存失败', content: error.message, showCancel: false})
    } finally {
      wx.hideLoading()
    }
  },

  previewReference() {
    if (this.data.referencePhotoUrl) wx.previewImage({current: this.data.referencePhotoUrl, urls: [this.data.referencePhotoUrl]})
  },

  toggleRecording() {
    if (this.data.recording) {
      recorder.stop()
      this.stopRecordTimer()
      this.setData({recording: false, transcribing: true})
      return
    }
    if (!this.data.consented) {
      return wx.showModal({title: '需要明确同意', content: '录音前必须获得对方明确同意。', showCancel: false})
    }
    wx.authorize({
      scope: 'scope.record',
      success: () => this.startRecording(),
      fail: () => wx.showModal({
        title: '需要麦克风权限',
        content: '请在小程序设置中允许使用麦克风。',
        confirmText: '打开设置',
        success: result => { if (result.confirm) wx.openSetting() }
      })
    })
  },

  startRecording() {
    this.setData({recording: true, recordSeconds: 0, analysis: null})
    this.recordTimer = setInterval(() => this.setData({recordSeconds: this.data.recordSeconds + 1}), 1000)
    recorder.start({
      duration: 60000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: 'mp3'
    })
  },

  stopRecordTimer() {
    if (this.recordTimer) clearInterval(this.recordTimer)
    this.recordTimer = null
  },

  async transcribeRecording(filePath) {
    this.stopRecordTimer()
    this.setData({recording: false, transcribing: true})
    try {
      const data = await api.upload('/ai/transcribe', filePath, 'audio')
      const text = String(data.transcript || '').trim()
      const transcript = [this.data.transcript.trim(), text].filter(Boolean).join('\n')
      this.setData({transcript, analysis: null})
      wx.showToast({title: text ? '转写完成' : '未识别到语音', icon: 'none'})
    } catch (error) {
      wx.showModal({title: '语音转写失败', content: error.message, showCancel: false})
    } finally {
      this.setData({transcribing: false, recordSeconds: 0})
    }
  },

  async analyze() {
    if (!this.data.transcript.trim()) return wx.showToast({title: '请先录音或输入真实对话', icon: 'none'})
    this.setData({analyzing: true})
    try {
      const data = await api.post('/ai/analyze-transcript', {transcript: this.data.transcript.trim()})
      this.setData({analysis: data.result, nextAction: data.result.next_action || ''})
    } catch (error) {
      wx.showModal({title: '分析不可用', content: error.message, showCancel: false})
    } finally {
      this.setData({analyzing: false})
    }
  },

  async save() {
    if (!this.data.consented) return wx.showToast({title: '请确认已获得明确同意', icon: 'none'})
    if (!this.data.selectedContact) return wx.showToast({title: '请选择联系人', icon: 'none'})
    if (!this.data.transcript.trim()) return wx.showToast({title: '请录入真实对话', icon: 'none'})
    try {
      await api.post('/conversations', {
        contact_id: this.data.selectedContact.id,
        transcript: this.data.transcript.trim(),
        summary: this.data.analysis ? this.data.analysis.summary : '',
        next_action: this.data.nextAction,
        score: this.data.analysis ? this.data.analysis.score : this.data.selectedContact.score
      })
      if (this.data.analysis) {
        await api.patch(`/contacts/${this.data.selectedContact.id}`, {
          interests: this.data.analysis.interests || [],
          score: this.data.analysis.score
        })
      }
      this.setData({transcript: '', analysis: null, nextAction: ''})
      wx.showToast({title: '交流记录已保存'})
    } catch (error) {
      wx.showModal({title: '保存失败', content: error.message, showCancel: false})
    }
  }
})
