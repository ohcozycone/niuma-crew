# 静态头像历史验证

记录范围：原段落标注的历史版本；2026-10-23 仅整理归属，未重做视觉或真实服务验收。

此前十角色阶段的纯图片选择界面调整通过修改文件格式检查、类型检查、lint、6 项现有头像测试与生产构建。开发界面在日间/夜间的 1440、390、320px 视口均无横向溢出；十张图片逐一选择、重开回显、键盘选择及关闭后焦点恢复通过，无页面异常。浏览器使用隔离 API 数据，未执行后端写入；证据见[本次验证](../../../niuma-crew-archive/output/reviews/avatar-picker-images/verification.json)。

此前十角色阶段的正方形选项调整：修改样式格式检查与生产构建通过。日间/夜间 1440、390、320px 的十个选项均实测宽高一致、图片居中，无横向溢出；选图回显与键盘操作通过，见[正方形布局验证](../../../niuma-crew-archive/output/reviews/avatar-picker-square/verification.json)。

本轮十三角色与默认切换：17 个测试文件、118 项测试、类型检查、lint 和生产构建通过；十三角色真实 SSR 与母版 RGBA 零差异。隔离 API 的生产浏览器回归覆盖新建默认实习牛、纯图片选择/保存/回显、后端/前端头像对话展示、历史 ID 保留与手机布局，见[当前页面验证](../../../niuma-crew-archive/output/avatar-svg-adoption/browser-check.json)。
