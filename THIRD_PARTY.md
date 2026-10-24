# 依赖与研究来源

本版新增匹配、SIPP、区间预约、拓扑和协调代码为项目内Python实现，没有下载、复制、链接或分发下列外部MAPF求解器源码；因此不存在宣称已集成作者原项目的固定SHA。下列论文用于算法思路与适用边界，性能只以本项目基准为准。

- [SIPP，Phillips与Likhachev，ICRA 2011](https://www.cs.cmu.edu/~maxim/files/sipp_icra11.pdf)：安全区间表示。项目另适配多路点、原子服务与字典序成本。
- [CBS研究入口](https://jiaoyangli.me/portfolio/cbs/)：冲突约束与局部修复思路；未实现完整走廊对称推理。
- [CBS-TA/ECBS-TA，AAMAS 2018](https://whoenig.github.io/publications/2018_AAMAS_a_Hoenig.pdf)：分配与路径联动背景；本版是有限候选方案，没有继承论文理论保证。
- [RHCR作者仓库](https://github.com/Jiaoyang-Li/RHCR)：滚动协调背景；本版窗口模式为自主实验实现，不是移植。
- [libMultiRobotPlanning](https://github.com/whoenig/libMultiRobotPlanning)、[PIBT](https://github.com/Kei18/pibt2)、[LaCAM](https://github.com/Kei18/lacam0)是研究过的候选，没有随本版打包。
- [EECBS](https://github.com/Jiaoyang-Li/EECBS)、[MAPF-LNS2](https://github.com/Jiaoyang-Li/MAPF-LNS2)、[ITA-CBS2](https://github.com/TachikakaMin/ITA-CBS2)不作为本版组件；原方案记录了研究许可/GPL等差异，未来集成须逐项固定源码和核对许可，不能按MIT笼统处理。

Three.js/OrbitControls沿用`frontend/vendor/`原有许可证和版本清单；Python依赖沿用requirements，不新增科学计算或原生求解依赖。安装版本由`requirements.txt`固定；交付不包含本机`.venv`，请在目标机器重新安装。

保留的MovingAI仓库图来自[MovingAI MAPF数据](https://www.movingai.com/benchmarks/mapf/index.html)，按原有[ODC Attribution 1.0](https://opendatacommons.org/licenses/by/1-0/)归属说明保留；项目另外配置业务取送点，结果不是官方.scen成绩。新增三张图由`map_support/generator.py`本地生成，生成参数保存在地图metadata及生成脚本。

Logo与界面沿用项目已确认的AW素材；交付保留程序读取的SVG与ICO。本版不依赖`.temp`或联网CDN素材。
