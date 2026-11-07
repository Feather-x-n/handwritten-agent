import { createApp } from 'vue'
import App from './App.vue'

// 当前只有一个页面，用不到 router / pinia / element-plus，直接挂载即可。
// 以后如果页面变多，再在这里注册 app.use(router) 等插件。
createApp(App).mount('#app')
