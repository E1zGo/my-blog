const blogConfig = {
  author: 'E1zGo',                          // 改成你的名字/昵称
  title: 'E1zGo',                           // 改成你的博客名
  subtitle: 'Code and Life',        // 改成你喜欢的slogan
  description: '山前山后各有风景',
  avatar: '/avatar.png',                    // 把你的头像图片放到 public/avatar.png
  siteUrl: 'https://e1zgo.top',            // 你的域名，用于SEO
  socials: {
    github: 'https://github.com/E1zGo',    // 改成你的 GitHub
    twitter: 'https://twitter.com/E1zGo',  // 没有就留空 ''
    email: 'faceit.rq@foxmail.com',               // 改成你的邮箱
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
    comments: false,
  },
}

export default blogConfig