const { getApiBaseUrl } = require('../config')

function errorMessage(data, fallback) {
  if (!data) return fallback
  if (typeof data.detail === 'string') return data.detail
  if (Array.isArray(data.detail)) return data.detail.map(item => item.msg || String(item)).join('；')
  return fallback
}

function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync('token')
    const header = {'content-type': 'application/json'}
    if (token) header.Authorization = 'Bearer ' + token
    wx.request({
      url: getApiBaseUrl() + path,
      method: options.method || 'GET',
      data: options.data,
      header,
      timeout: options.timeout || 20000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) return resolve(res.data)
        if (res.statusCode === 401 && token && !path.startsWith('/auth/')) {
          wx.removeStorageSync('token')
          wx.reLaunch({url: '/pages/login/login'})
        }
        reject(new Error(errorMessage(res.data, `请求失败（${res.statusCode}）`)))
      },
      fail(error) {
        reject(new Error(error.errMsg || '无法连接 ExpoMind 服务'))
      }
    })
  })
}

function upload(path, filePath, name = 'image', formData = {}) {
  return new Promise((resolve, reject) => wx.uploadFile({
    url: getApiBaseUrl() + path,
    filePath,
    name,
    formData,
    timeout: 120000,
    header: {Authorization: 'Bearer ' + wx.getStorageSync('token')},
    success(res) {
      let data = {}
      try { data = JSON.parse(res.data || '{}') } catch (error) { data = {detail: res.data} }
      if (res.statusCode >= 200 && res.statusCode < 300) return resolve(data)
      reject(new Error(errorMessage(data, `上传失败（${res.statusCode}）`)))
    },
    fail(error) {
      reject(new Error(error.errMsg || '上传失败'))
    }
  }))
}

function absoluteUrl(path) {
  if (!path) return ''
  if (/^https?:\/\//i.test(path)) return path
  const origin = getApiBaseUrl().replace(/\/api\/?$/i, '')
  return origin + (path.startsWith('/') ? path : '/' + path)
}

function imagePath(path) {
  if (!path) return Promise.resolve('')
  const url = absoluteUrl(path)
  return new Promise(resolve => wx.getImageInfo({
    src: url,
    success(result) { resolve(result.path || url) },
    fail() { resolve(url) }
  }))
}

module.exports = {
  request,
  get: path => request(path),
  post: (path, data) => request(path, {method: 'POST', data}),
  patch: (path, data) => request(path, {method: 'PATCH', data}),
  del: path => request(path, {method: 'DELETE'}),
  upload,
  absoluteUrl,
  imagePath
}
