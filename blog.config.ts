const blogConfig = {
  author: 'Your Name',
  title: 'MyBlog',
  subtitle: '写代码，写文字，写生活。',
  description: '一个热爱技术与写作的开发者，记录技术思考、生活感悟与项目实践。',
  avatar: '/avatar.png',
  socials: {
    github: 'https://github.com/yourusername',
    twitter: 'https://twitter.com/yourusername',
    email: 'you@example.com',
  },
  postsPerPage: 6,
  nav: [
    { label: '首页', path: '/' },
    { label: '文章', path: '/posts' },
    { label: '标签', path: '/tags' },
    { label: '关于', path: '/about' },
  ],
  features: {
    darkMode: true,
    search: true,
    toc: true,
    readingProgress: true,
    comments: false,   // 配置好 GiscusComment.vue 后改为 true
  },
}

export default blogConfig
