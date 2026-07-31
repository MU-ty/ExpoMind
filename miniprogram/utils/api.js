const { API_BASE_URL } = require('../config')
function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: API_BASE_URL + path,
      method: options.method || 'GET',
      data: options.data,
      header: {'content-type':'application/json', Authorization: wx.getStorageSync('token') ? 'Bearer ' + wx.getStorageSync('token') : ''},
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) return resolve(res.data)
        if (res.statusCode === 401) { wx.removeStorageSync('token'); wx.reLaunch({url:'/pages/login/login'}) }
        reject(new Error((res.data && res.data.detail) || '请求失败'))
      },
      fail: reject
    })
  })
}
function upload(path, filePath, name = 'image') {
  return new Promise((resolve, reject) => wx.uploadFile({
    url: API_BASE_URL + path, filePath, name,
    header: {Authorization:'Bearer ' + wx.getStorageSync('token')},
    success(res) { const data = JSON.parse(res.data || '{}'); if (res.statusCode >= 200 && res.statusCode < 300) resolve(data); else reject(new Error(data.detail || '上传失败')) },
    fail: reject
  }))
}
module.exports = {get:path=>request(path), post:(path,data)=>request(path,{method:'POST',data}), patch:(path,data)=>request(path,{method:'PATCH',data}), del:path=>request(path,{method:'DELETE'}), upload}
