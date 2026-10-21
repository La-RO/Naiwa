# Naiwa Club 本地官网

一个展示互联网奶蛙图片和视频的静态网站。包含 4 个图片分区、图片搜索、分类筛选、大图预览、独立视频放映室和逐项素材来源。

## 最快打开方法

1. 完整解压整个网站压缩包。
2. 打开 `naiwa-club-local` 文件夹。
3. 双击 `index.html`，用 Chrome、Edge、Firefox 或 Safari 浏览。

请保留 `assets`、`data`、`styles.css` 和 `app.js` 与首页之间的目录关系。图片、视频、字体样式和页面脚本都在本地；查看外部来源及 Instagram 需要联网。

## 通过本地服务器运行

如果电脑装有 Python 3，在网站文件夹中执行：

```bash
python3 serve.py
```

Windows 也可以执行：

```powershell
py -3 serve.py
```

浏览器会打开 `http://127.0.0.1:8000`。使用完毕后，在终端按 `Ctrl+C` 停止。无需安装第三方依赖，也无需 npm。

如需更换端口：

```bash
python3 serve.py --port 8080
```

## 网站内容

- 日常表情：6 张。
- 奶蛙名画：6 张。
- 穿搭与变体：6 张。
- 出没现场：6 张。
- 奶蛙放映室：3 段本地视频。
- 每张图片及每段视频均附来源入口；详情中可查看原始资源。
- 完整素材来源清单：`sources.html`。
- Instagram：`unimelb.naiwaclub`。

## 修改内容

- 页面结构：`index.html`。
- 页面样式：`styles.css`。
- 分类、搜索及大图预览：`app.js`。
- 图片清单：`data/images.json`。
- 视频清单：`data/videos.json`。
- 本地图片与视频：`assets/gallery/`、`assets/videos/`。
- 浏览器读取的数据：`data/catalogue.js`。

修改 JSON 清单后，执行下面的命令重新生成浏览器数据文件：

```bash
python3 update_catalogue.py
```

图片和视频来自公开互联网来源，原始地址及收录说明保留在清单中。分区为本网站整理，不代表来源平台的官方分类。未能核实的原创作者和授权信息没有被补写为事实。

## 本版本验证范围

已检查 24 张图片文件、3 段 H.264 视频、相对素材路径、分类与搜索逻辑、空结果提示、大图切换、视频预览与关闭、手机导航的交互逻辑、完整来源清单，以及本地服务器的视频分段读取。当前制作环境的浏览器预览服务不可用，未完成实际浏览器的视觉检查和视频播放检查。
