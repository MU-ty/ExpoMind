Component({
  data: {
    selected: 0,
    hidden: false,
    items: [
      {pagePath: '/pages/home/home', text: '首页', icon: '⌂'},
      {pagePath: '/pages/contacts/contacts', text: '联系人', icon: '◎'},
      {pagePath: '/pages/capture/capture', text: '现场', icon: '●'},
      {pagePath: '/pages/tasks/tasks', text: '跟进', icon: '✓'},
      {pagePath: '/pages/settings/settings', text: '我的', icon: '○'}
    ]
  },
  methods: {
    switchTab(event) {
      const {path, index} = event.currentTarget.dataset
      if (Number(index) === this.data.selected) return
      wx.switchTab({url: path})
    }
  }
})
