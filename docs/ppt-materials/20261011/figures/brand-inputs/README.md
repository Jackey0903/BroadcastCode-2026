# 架构图品牌参考素材

这些输入仅用于答辩架构图的品牌构图；业务前端素材未修改。

- GameBuddy篮球小人来自仓库现有`product/watch/companions/game-buddy/assets/game-buddy-crt.webp`，选用第一行第一列的正面站立造型作为图像生成参考。原精灵格为192×208像素。
- [AWS彩色Logo原始PNG](https://a0.awsstatic.com/libra-css/images/logos/aws_logo_smile_179x109.png)保存为`aws-logo-small.png`，使用深色字标与橙色笑脸。
- [NBA原始SVG](https://cdn.nba.com/logos/leagues/logo-nba.svg)保存为`nba-logo.svg`；`nba-logo.png`由rsvg-convert按512像素高度原样渲染，供图像生成工具读取。架构图使用其左侧红蓝徽标作为参考。

最终整图通过内置图像生成工具编辑，并非逐像素拼贴原始Logo。原始输入及哈希见`source-manifest.json`。
