# CabinLingo 动效资源

- Lottie JSON 动画建议放在 `src/assets/animations/lottie/`。
- Rive `.riv` 文件建议放在 `src/assets/animations/rive/`。
- 页面动画通过 `@/motion` 中的 Vue composable 调用。
- 页面卸载时会清理动画实例；用户启用“减少动态效果”时会暂停或不启动动效。
- 简单悬停、聚焦和按钮状态优先使用 CSS。
