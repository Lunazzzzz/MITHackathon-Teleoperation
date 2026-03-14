# OmniHand 已读摘要

更新时间: 2026-03-09

## 记录目的

保存当前已经确认过的项目资料信息，后续继续讨论时可直接读取本文件。

## 相关路径

- 项目根目录: `C:\Users\33590\Desktop\RA项目\控制机械臂垃圾分类项目`
- 灵巧手工具目录: `C:\Users\33590\Desktop\RA项目\控制机械臂垃圾分类项目\智元灵巧手\OmniHandBox-2-5`
- 灵巧手说明书: `C:\Users\33590\Desktop\RA项目\控制机械臂垃圾分类项目\智元灵巧手\智元OmniHand 灵动款 2025 灵巧.pdf`
- 机械臂参数目录: `C:\Users\33590\Desktop\RA项目\控制机械臂垃圾分类项目\松灵NERO机械臂参数`

## 当前对项目结构的判断

这个目录目前更像“硬件资料集合”，不是完整的软件源码仓库。

已看到的两部分资料:

- 智元 OmniHand 灵巧手的上位机工具和说明书
- 松灵 NERO 机械臂相关链接/参数文件

当前没有发现其他源码目录直接引用 OmniHand 工具，说明它大概率是独立放入项目中的厂家配套软件。

## OmniHandBox-2-5 目录结论

`OmniHandBox-2-5` 不是源码工程，更像已经打包好的 Windows 控制软件目录。

关键判断依据:

- 主程序为 `OmniHand-ToolBox.exe`
- 目录内包含大量 `Qt6*.dll`、`platforms`、`styles`、`translations` 等 Qt 运行时文件
- 存在 `zlgcan.dll`、`kerneldlls`、`devices_property`，说明包含 CAN/CAN-FD 相关驱动
- 存在 `actions.json`、`LeftAction.json`、`RightAction.json`，说明软件支持预设动作/手势

## 动作文件内容

### actions.json

包含通用或基础动作，例如:

- 右打开
- 打开
- 握拳
- 零位

每个动作对应 `pos_axis_1` 到 `pos_axis_12` 的目标值。

### LeftAction.json

包含左手动作，例如:

- 左手OK
- 左手Rock
- 左手三
- 左手半张
- 左手合
- 左手大拇指与小指对指
- 左手大拇指与无名指对指
- 左手张
- 左手捏卡片-1 / 左手捏卡片-2
- 左手捏瓶盖-1 / 左手捏瓶盖-2
- 左手握
- 左手比心
- 左手爱心

### RightAction.json

包含右手动作，例如:

- 右手OK
- 右手Rock
- 右手三
- 右手半张
- 右手合
- 右手大拇指与小指对指
- 右手大拇指与无名指对指
- 右手张
- 右手捏卡片-1 / 右手捏卡片-2
- 右手捏瓶盖-1 / 右手捏瓶盖-2
- 右手握
- 右手比心
- 右手爱心

说明:

- 文件里主要实际使用的是 `pos_axis_1` 到 `pos_axis_10`
- `pos_axis_11` 和 `pos_axis_12` 在已看到的数据中为 0
- 动作值范围通常在 `0-4096`

## 通讯与驱动结论

从 `kerneldlls\dll_cfg.ini` 和相关 DLL 判断:

- 工具支持 ZLG 的 CAN / CAN-FD 设备
- 目录中存在 `USBCAN.dll`、`USBCANFD.dll`、`CANFDNET.dll`、`CANFDCOM.dll` 等文件
- 工具大概率通过 CAN 总线与灵巧手通信

## PDF 说明书关键信息

文件名:

- `智元OmniHand 灵动款 2025 灵巧.pdf`

基本信息:

- 共 31 页
- 文档标题: 《智元 OmniHand 灵动款 2025 灵巧手 产品使用说明书》
- 版本号: `1.6`
- 元数据创建时间: `2026-02-13 11:26:52 +08:00`
- 生成工具: `WPS 文字`

### 说明书目录要点

主要章节包括:

- 重要安全须知
- 产品简介
- 安装说明
- 通讯协议说明
- 上位机使用说明

### 产品定位

OmniHand 灵动款 2025 是一款紧凑型高自由度交互灵巧手，适用于小尺寸人形机器人。

手册中明确提到:

- 适合身高 `110~130 cm` 的机器人
- 支持手势交互、触摸交互、轻作业
- 覆盖手心、手背和五指 `300+` 点位触觉感应

### 主要参数

- 重量: `<=510g` / 触觉款 `<=520g`
- 尺寸: `180 * 85 * 38.5 mm`
- 主动自由度: `10`
- 总自由度: `16`
- 最小张开/闭合时间: `0.5s / 0.5s`
- 指尖重复定位精度: `0.3 mm`
- 五指抓握力: `>=5 kg`
- 工作电压: `18-27V`
- 通讯接口: `CAN-FD / RS485`
- 工作温度范围: `0~45C`
- 支持 OTA 在线升级

### 自由度说明

手册给出:

- 主动自由度 10
- 总自由度 16
- 大拇指 3 个主动自由度
- 食指 2 个主动自由度
- 中指 1 个主动自由度
- 无名指 2 个主动自由度
- 小指 2 个主动自由度

### 触觉相关

触觉款参数中提到:

- 指尖 + 手掌 + 手背一维力感知
- 阵列分辨率 `0.1N`
- 感知范围 `0~20N`
- 最大接受力 `200N`

### 装箱与接口

装箱清单中提到:

- 灵巧手本体
- 电源 + CANFD 通讯线
- RS485 通讯线
- USB Type-C 通讯线

供电与连接:

- 需要用户自备 `24V` 电源
- 支持 `CAN-FD`
- 支持 `RS485`
- 支持通过 `USB` 连接上位机

### 二次开发信息

说明书写明:

- 支持基于 `CAN-FD / RS485` 进行二次开发
- SDK 文档仓库: `https://github.com/AgibotTech/Omnihand-2025-SDK`

### CAN-FD 关键参数

手册中提到:

- 仲裁域波特率 `1M`
- 数据域波特率 `5M`
- 仅支持 `CAN-FD` 帧格式
- 对经典 `CAN2.0` 帧:
  - 不解析数据
  - 不返回应答
  - 不产生错误帧

默认节点说明:

- CAN 默认节点 ID: `0x09`
- 可使用 `0x7FF` 查询节点 ID

### USB/串口关键参数

使用 USB 时会虚拟串口，参数为:

- 波特率 `460800`
- 8 数据位
- 无校验
- 1 停止位

串口默认节点说明:

- USB/串口默认 ID: `0x01`
- `0x7FF` 为广播地址

### 协议/控制说明

手册中给出:

- CAN-FD 帧格式
- USB/串口帧格式
- CRC16 算法示例代码
- 设置单个/全部电机位置的示例
- 读取传感器数据的指令
- 读取版本号、序列号、设备型号等指令

控制建议:

- 建议机器人本体控制时使用“位置 + 力矩”复合模式
- 不建议频繁抓握
- 抓取间隔建议 `>=2s`

### 指示灯与热插拔

- 手背灯蓝色: 正在初始化
- 手背灯绿色: 初始化结束
- 若电压异常，蓝灯可能无法变绿
- 整手不支持热插拔

### 上位机软件要求

运行环境:

- Windows `10/11`
- CPU: `Intel Core i5 8代以上`
- 内存: `8GB+`
- 显示: 支持 `OpenGL 3.3+`
- 接口: `USB 2.0+`
- 软件依赖:
  - `VC++ 2019 Redistributable`
  - `.NET Framework 4.8`

### 上位机使用要点

- 软件名: `OmniHand-ToolBox`
- 双击即可运行
- 登录界面无需用户名和密码
- 支持中英文切换
- 连接后会自动搜索端口
- 波特率固定 `460800`
- 可查看关节位置、力矩、转速、电流、温度

### 控制面板能力

上位机支持:

- 逐关节调节
- 一键执行所有关节目标值
- 一键回初始位置
- 保存当前姿态为自定义动作
- 动作编组播放
- 动作循环执行
- 导出 JSON 动作文件
- 导入 JSON 动作文件

### 压力矩阵

手册中说明:

- 可查看五指指尖、手心、手背压力
- 指尖压力测点显示为合成点
- 可显示各区域总压力

### 固件升级

- 可在上位机中查询版本号
- 可选择 `*.bin` 文件进行升级
- 升级日志会提示是否 OTA 成功
- 若失败可重试

### 手册末尾版本基准

本手册基于以下版本编写:

- 硬件版本: `Ver.3.0.0`
- 固件版本: `Ver.1.1.9`
- 上位机软件版本: `Ver.2.3.0`

## 与当前项目的关系判断

当前可以把该目录理解为:

- `松灵 NERO 机械臂` 负责机械臂本体
- `智元 OmniHand` 负责末端灵巧手

也就是说，这个总目录更像是“垃圾分类机器人所需硬件资料包”，其中灵巧手部分目前主要提供:

- 官方说明书
- 上位机控制工具
- 预设动作 JSON
- 通讯驱动

## 后续建议的读取方式

后续如果用户提到下列关键词，优先读取本文件:

- OmniHand
- 智元灵巧手
- OmniHandBox
- 灵巧手说明书
- 动作 JSON
- CAN-FD / RS485 / USB 串口控制

## 备注

如果后续又补充了新的截图、源码、SDK 或测试结论，应继续追加到本目录下的新文件中，避免信息分散。

---

## 补充记录: 松灵 NERO 机械臂

更新时间: 2026-03-09

### 本地文件夹内容

目录:

- `C:\Users\33590\Desktop\RA项目\控制机械臂垃圾分类项目\松灵NERO机械臂参数`

已看到文件:

- `松灵GitHub.txt`
- `用户手册网址.txt`

对应内容:

- GitHub 组织: `https://github.com/agilexrobotics`
- 用户手册网址: `https://agilexsupport.yuque.com/staff-hso6mo/alxgtf/air57k7k3nhgeuxb`

### 当前判断

虽然本地只有一个语雀手册链接，没有手册正文，但结合文件夹命名 `松灵NERO机械臂参数`，以及 AgileX 官方公开资料，可以较高置信度判断这个手册对应的机械臂就是:

- `AgileX / 松灵 NERO`

说明:

- 官方产品页存在 `NERO` 产品
- 官方描述为面向 embodied AI / humanoid robotics 的机械臂
- 官方参数页显示其为 `7-DoF` 机械臂

### 官方产品页关键信息

来源: `https://global.agilex.ai/products/nero`

可确认的信息:

- 产品名: `NERO`
- 类型: 机械臂 / humanoid robot arm
- 自由度: `7-DoF`
- 负载: `3.0 kg`
- 臂展: `580 mm`
- 重复精度: `0.1 mm`
- 机身重量: 文案中提到 `4.8 kg`
- 通信/控制: 支持 `CAN / HTTP / TCP`
- 软件生态: 支持 `Python SDK`、`ROS1 / ROS2`

### GitHub 对应仓库

#### 1. pyAgxArm

仓库:

- `https://github.com/agilexrobotics/pyAgxArm`

重要结论:

- 这是 AgileX 新版 Python SDK
- README 明确写到同时支持 `Piper` 和 `Nero`
- 文中原话含义为: 该 SDK 支持 Piper、Nero、AgxGripper、Revo2 等设备

关键用法示例:

- `create_agx_arm_config(robot="nero", comm="can", channel="can0")`

说明:

- 如果后续你要直接写 Python 控制 NERO，这个仓库应优先看

#### 2. agx_arm_ros

仓库:

- `https://github.com/agilexrobotics/agx_arm_ros`

重要结论:

- 这是 AgileX 机械臂 ROS2 驱动
- README 明确写到支持 `Piper、Nero 等`
- 适合后续接 ROS2、MoveIt、URDF、驱动节点

说明:

- 如果后续你的垃圾分类系统要接 ROS2 控制机械臂，这个仓库应优先看

#### 3. NERO 首次使用 CAN 指南

文档路径:

- `https://github.com/agilexrobotics/pyAgxArm/blob/master/docs/nero/first_time_user_guide_can.md`

可确认的信息:

- NERO 首次使用推荐环境: `Ubuntu 20.04 / 22.04 / 24.04`
- Python: `>= 3.8`
- 需要 `can-utils`
- 需要 `CAN 转 USB` 模块
- 官方流程包括:
  - 激活 `can0`
  - 给机械臂上电
  - 等待指示灯变绿
  - 在 NERO 网页上位机中打开 `CAN 推送`
  - 用 `candump can0` 检查是否有数据

这说明:

- NERO 的底层接入方式与当前项目里的 OmniHand 一样，至少都能走 CAN 方向集成

### 与 Piper 的关系

当前 GitHub 上机械臂老资料很多仍以 `Piper` 命名，例如:

- `piper_sdk`
- `piper_ros`
- `Piper_sdk_ui`
- `piper_sdk_demo`

但更新后的官方 SDK `pyAgxArm` 已明确纳入 `Nero` 支持。

因此更合理的使用优先级是:

1. 新项目优先看 `pyAgxArm`
2. ROS2 集成优先看 `agx_arm_ros`
3. `piper_*` 仓库作为历史资料或相似参考

### 当前可下的结论

如果你这个本地“用户手册网址”确实是 NERO 那份手册，那么它在 GitHub 上最对应的官方仓库不是底盘仓库，而是下面两个:

- `https://github.com/agilexrobotics/pyAgxArm`
- `https://github.com/agilexrobotics/agx_arm_ros`

### 后续查找建议

后续如果用户提到以下关键词，优先联想到 NERO 资料:

- NERO
- 松灵机械臂
- AgileX arm
- pyAgxArm
- agx_arm_ros
- CAN 控制机械臂

### 本地已下载仓库

为后续实现 “NERO 机械臂 + OmniHand 灵巧手联合抓取”，已在本地目录下载以下官方仓库:

- `C:\Users\33590\Desktop\RA项目\控制机械臂垃圾分类项目\第三方仓库\pyAgxArm`
- `C:\Users\33590\Desktop\RA项目\控制机械臂垃圾分类项目\第三方仓库\agx_arm_ros`
- `C:\Users\33590\Desktop\RA项目\控制机械臂垃圾分类项目\第三方仓库\Omnihand-2025-SDK`

对应远端地址:

- `https://github.com/agilexrobotics/pyAgxArm.git`
- `https://github.com/agilexrobotics/agx_arm_ros.git`
- `https://github.com/AgibotTech/Omnihand-2025-SDK.git`

下载时确认到的提交号:

- `pyAgxArm`: `b4fe1e7`
- `agx_arm_ros`: `1c1d90e`
- `Omnihand-2025-SDK`: `bcbccf4`

当前用途判断:

- `pyAgxArm`: NERO 机械臂 Python 直接控制
- `agx_arm_ros`: NERO 机械臂 ROS2 集成
- `Omnihand-2025-SDK`: OmniHand 灵巧手二次开发

---

## 补充记录: 抓取项目当前需求约束

更新时间: 2026-03-09

### 目标描述

目标是将:

- NERO 机械臂
- OmniHand 灵巧手
- Intel RealSense D435 深度相机

组合成一个固定场景下的桌面抓取与分类系统。

当前理解的任务流程:

1. 固定相机观测桌面
2. 识别物体类别和位置
3. 将视觉坐标转换为机械臂坐标
4. 机械臂移动到抓取点
5. 灵巧手抓取物体
6. 按类别放到指定投放点

### 当前已确认约束

- 相机型号: `Intel RealSense D435`
- 相机位置: 固定安装
- 抓取高度: 第一版计划测试后写死
- 第一版目标物体:
  - 空矿泉水瓶
  - 水杯
- 目标物体姿态:
  - 默认躺着放
  - 默认圆柱体
  - 无把手
- 桌面任务模式:
  - 一次只处理一个物体
- 第一版投放点数量:
  - 2 个
  - 矿泉水瓶一个
  - 水杯一个
- 用户偏好:
  - 希望 Windows 处理大部分工作
  - 最终可以接受 Ubuntu

### 当前技术建议

基于现有 SDK 文档，建议采用“两阶段 / 混合式”路线:

#### 阶段 1: Windows 为主

Windows 负责:

- D435 取流
- 数据采集
- YOLO 训练与推理验证
- 标注 / 调试界面
- 桌面坐标系验证

说明:

- Windows 很适合前期视觉调试与数据准备
- RealSense 和 YOLO 在 Windows 上做验证成本较低

#### 阶段 2: Ubuntu 负责硬件执行

Ubuntu 负责:

- NERO 机械臂控制
- OmniHand 灵巧手控制
- 最终自动抓取执行

说明:

- `pyAgxArm` 文档明确主支持 `Ubuntu`
- `Omnihand-2025-SDK` 明确要求 `Ubuntu 22.04 x86_64`
- `pyAgxArm` 代码中 `CanComm` 在 Windows 分支直接返回 `None`
- 因此 Windows 不适合作为最终机械臂 + 灵巧手联控主控环境

### 相机安装建议

当前建议第一版优先使用:

- `俯视安装`

原因:

- 桌面平面标定更简单
- 物体位置换算更直接
- 抓取高度写死时更容易稳定
- 目标物体只有两类，且一次只处理一个，暂时不需要复杂视角

### 第一版抓取策略建议

灵巧手第一版建议只做一个通用抓取动作:

- 张开
- 到预抓取位
- 下探到固定抓取高度
- 闭合
- 抬起
- 送到投放点
- 张开放下

说明:

- 第一版不要一开始就做多手势、多抓取策略切换
- 先把“能稳定抓起并放到目标区”跑通更重要

### 当前硬件接口判断

根据 SDK 文档:

- NERO 机械臂:
  - 需要 `USB 转 CAN` 模块
  - 官方文档按 `CAN` 控制说明
- OmniHand 灵巧手:
  - 需要 `ZLG USBCANFD` 系列设备
  - 推荐型号:
    - `USBCANFD-100U-mini`
    - `USBCANFD-100U`
    - `USBCANFD-200U`

注意:

- 当前只能确认“项目需要这些模块”
- 不能从现有本地文件判断“用户手上是否实际已经有这些硬件”

### 后续优先事项

建议后续优先完成:

1. 确认手头是否有 NERO 的 USB-CAN 模块
2. 确认手头是否有 OmniHand 对应的 ZLG USBCANFD 模块
3. 确认 D435 的固定安装位置和视野范围
4. 在 Windows 上先验证视觉检测
5. 在 Ubuntu 上分别跑通机械臂和灵巧手单独控制
