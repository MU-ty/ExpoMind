const ENVIRONMENTS = {
  // WeChat DevTools can reach the Docker service on the host through localhost.
  develop: 'http://172.16.123.61:8088/api',
  // Replace these two values with the HTTPS domain registered in WeChat.
  trial: 'https://expo.your-company.com/api',
  release: 'https://expo.your-company.com/api'
}

function getEnvVersion() {
  try {
    return wx.getAccountInfoSync().miniProgram.envVersion || 'develop'
  } catch (error) {
    return 'develop'
  }
}

function getApiBaseUrl() {
  const override = typeof wx !== 'undefined' ? wx.getStorageSync('apiBaseUrl') : ''
  return String(override || ENVIRONMENTS[getEnvVersion()] || ENVIRONMENTS.develop).replace(/\/$/, '')
}

function isLocalDevelopment() {
  return getEnvVersion() === 'develop'
}

module.exports = { ENVIRONMENTS, getApiBaseUrl, getEnvVersion, isLocalDevelopment }
