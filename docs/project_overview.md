# sort_trash 项目说明

## 1. 项目目标

`sort_trash` 是一个面向桌面目标抓取与分类的集成项目，目标是把以下几部分串起来：

- Intel RealSense 深度相机负责感知
- YOLO 模型负责目标检测
- 标定结果负责把相机坐标系转换到机械臂基座坐标系
- 松灵 NERO 机械臂负责末端位姿移动
- 智元 OmniHand 灵巧手负责执行开合与抓取

当前仓库既包含“整条抓取链路”的脚本，也包含若干“分步骤验证”的脚本，用于逐段联调相机、模型、标定、机械臂和灵巧手。

## 2. 系统架构

### 2.1 高层数据流

```text
RealSense 彩色/深度图
        |
        v
YOLO 检测目标框
        |
        v
深度采样 + 像素反投影
        |
        v
相机坐标点(camera XYZ)
        |
        v
标定矩阵 T_base_camera
        |
        v
机械臂基座坐标点(base XYZ)
        |
        v
抓取模板 / 悬停模板 / 放置模板
        |
        +------------------> NERO 机械臂位姿控制
        |
        +------------------> OmniHand 开/合控制
```

### 2.2 通信链路

- 相机: `pyrealsense2`
- 机械臂: `pyAgxArm` 通过 `socketcan` 控制 `can0`
- 灵巧手: `omnihand_2025` Python 绑定，当前项目已适配 `serial` 串口模式，可走 `/dev/ttyACM0`
- 配置中心: YAML

## 3. 目录与模块

### 3.1 顶层目录

- `config/`: 项目配置、标定文件、工作空间参数
- `environment/`: Conda 环境文件和初始化脚本
- `scripts/`: 主要业务脚本
- `pyAgxArm/`: 本地机械臂 Python SDK 副本，优先于系统安装版本使用
- `third_party/`: 外部厂商 SDK 与 ROS 仓库
- `assets/`: 资源文件
- `助手记录/`: 项目过程记录和背景资料

### 3.2 `scripts/` 分层

#### `scripts/control/`

控制层脚本，负责机械臂、灵巧手和抓取流程。

- `run_sort_trash_pipeline.py`
  - 主抓取流程骨架
  - 完成检测、点位转换、机械臂 approach/grasp/retreat/drop 和灵巧手开合联动
- `hover_detected_target.py`
  - 让机械臂末端持续悬停在目标上方
  - 适合调试目标跟随与 hover 位姿
- `pick_lying_bottle_template.py`
  - 面向“桌面横躺矿泉水瓶”的抓取模板
  - 生成 `hover / pregrasp / ingress / lift / retreat`
- `move_flange_pose.py`
  - 给定末端法兰位姿，直接驱动机械臂移动
- `sweep_cartesian_pose.py`
  - 从已知可达位姿开始，按小步长扫到目标位姿
  - 适合处理 `move_p` 对可达性敏感的问题
- `probe_cartesian_reachability.py`
  - 探测目标位姿是否可达
- `omnihand_smoke_test.py`
  - 灵巧手连接与开合自检脚本

#### `scripts/vision/`

视觉感知与推理层。

- `_common.py`
  - RealSense 管线构建、深度采样、设备选择、检测结果整理等通用函数
- `view_realsense_stream.py`
  - 仅查看 RealSense 彩色/深度流
- `detect_realsense_yolo_2d.py`
  - 仅做 2D 检测
- `detect_realsense_yolo_xyz.py`
  - 输出目标相机坐标或基座坐标
- `yolo_detect_realsense.py`
  - YOLO 实时推理演示
- `train_yolo11_trash.py`
  - YOLO 垃圾分类检测训练入口
- `yolo11.py`
  - 一份实验性质的 RealSense + YOLO 推理脚本

#### `scripts/calibration/`

眼在手外标定工具链。

- `generate_charuco_board.py`
  - 生成标定板
- `capture_eye_to_hand.py`
  - 采集标定样本
- `solve_eye_to_hand.py`
  - 用 OpenCV `calibrateHandEye` 求 `T_base_camera`
- `verify_eye_to_hand.py`
  - 验证标定质量
- `_common.py`
  - 标定工具公共函数

#### `scripts/dev/`

- `check_setup.py`
  - 环境与依赖自检
  - 可验证 Python、CUDA、YOLO、RealSense 枚举、`pyAgxArm` 等

#### `scripts/` 根目录核心模块

- `_local_sdk.py`
  - 优先把仓库内 `pyAgxArm` 加入 `sys.path`
  - 避免误用系统里其它版本 SDK
- `omnihand_2025_controller.py`
  - 项目内部的灵巧手控制封装
  - 负责解析 `hand` 配置、建立连接、发送关节角
- `omnihand_actions.py`
  - 面向协作者的轻量接口层
  - 暴露 `create_actions()`、`open_hand()`、`close_hand()`

## 4. 关键配置文件

### 4.1 `config/sort_trash_pipeline.example.yaml`

这是项目的主配置入口，当前包含：

- `model`: YOLO 权重路径
- `calibration_file`: 标定结果文件
- `camera`: 相机分辨率、帧率、序列号
- `workflow`: 目标类别与流程选项
- `robot`: 机械臂速度、姿态、home pose、接近/回撤偏移
- `hand`: 灵巧手通信方式、串口、手型、开合关节角
- `classes`: 各类别对应的投放位姿

### 4.2 其它配置

- `config/calibration.identity.yaml`
  - 单位矩阵示例，适合纯流程调试
- `config/robot_workspace.yaml`
  - 预留给机械臂工作空间约束

## 5. 硬件组成

### 5.1 当前项目涉及的主要硬件

- 机械臂: 松灵 `NERO`
- 灵巧手: 智元 `OmniHand 2025`
- 深度相机: Intel RealSense `D435`
- 主机环境: Ubuntu 22.04

### 5.2 硬件职责

- NERO 负责末端位姿控制
- OmniHand 负责最终抓取接触与包络
- D435 提供 RGB 图像和深度

### 5.3 当前通信方式

- NERO:
  - `CAN`
  - 默认脚本使用 `can0`
  - Python 控制库为 `pyAgxArm`
- OmniHand:
  - 当前项目实际已跑通 `serial`
  - 配置示例为 `/dev/ttyACM0`
  - Python 控制入口为 `omnihand_2025` + 项目封装
- D435:
  - 通过 `pyrealsense2` 访问

## 6. 使用到的主要技术与软件包

### 6.1 Python 与环境

- Python `3.10`
- Conda 环境文件: `environment/grasp-gpu.yml`

虽然环境文件默认名叫 `grasp-gpu`，但实际可以创建为任意环境名，例如 `myenv`。

### 6.2 感知与数值计算

- `torch`
- `torchvision`
- `torchaudio`
- `ultralytics`
- `pyrealsense2`
- `opencv-contrib-python`
- `numpy`
- `scipy`
- `pyyaml`
- `matplotlib`

### 6.3 机械臂控制

- `pyAgxArm`
  - 本仓库内置本地副本
  - 机械臂控制通过 `AgxArmFactory.create_arm(...)`
  - 当前项目主要使用笛卡尔位姿控制 `move_p`

### 6.4 灵巧手控制

- 厂商 SDK: `third_party/Omnihand-2025-SDK`
- Python 绑定包: `omnihand_2025`
- 项目封装:
  - `scripts/omnihand_2025_controller.py`
  - `scripts/omnihand_actions.py`

当前仓库已经在厂商 SDK 基础上做过适配，重点包括：

- 支持串口 `serial` 传输而不只依赖 CANFD
- 支持 Python 侧创建右手/左手实例
- 支持通过 YAML 配置开合角度

### 6.5 标定与几何

- OpenCV `calibrateHandEye`
- ChArUco 标定板
- 像素点 + 深度 -> 相机三维点反投影
- 刚体变换矩阵 `T_base_camera`

## 7. 当前主流程说明

### 7.1 标准抓取流程

1. RealSense 读取彩色图和深度图
2. YOLO 检测目标类别和框
3. 取检测框中心点附近深度
4. 反投影得到相机坐标点
5. 用标定矩阵换算成机械臂基座坐标
6. 根据抓取模板生成 hover / approach / grasp / retreat / drop 位姿
7. 控制机械臂移动到目标位置
8. 控制灵巧手执行张开或闭合
9. 将物体移动到类别对应投放点

### 7.2 当前更现实的联调模式

由于视觉链路在 WSL 中可能不稳定，当前更推荐分成两段联调：

1. 机械臂侧:
   - 由协作者负责判断是否到达目标位姿
2. 灵巧手侧:
   - 由本项目统一提供简单接口
   - 到位后只触发 `open_hand()` 或 `close_hand()`

## 8. 当前已经形成的接口

### 8.1 灵巧手协作接口

文件: `scripts/omnihand_actions.py`

可直接调用：

```python
import sys
sys.path.insert(0, "/root/sort_trash/scripts")

from omnihand_actions import create_actions

hand = create_actions("/root/sort_trash/config/sort_trash_pipeline.example.yaml")
hand.open_hand()
hand.close_hand()
```

也可以直接使用模块级函数：

```python
import sys
sys.path.insert(0, "/root/sort_trash/scripts")

from omnihand_actions import open_hand, close_hand

open_hand("/root/sort_trash/config/sort_trash_pipeline.example.yaml")
close_hand("/root/sort_trash/config/sort_trash_pipeline.example.yaml")
```

### 8.2 当前配置中的灵巧手参数

示例配置已经按当前联调状态设置为：

- `transport: serial`
- `serial_port: /dev/ttyACM0`
- `serial_baudrate: 460800`
- `hand_type: right`

并写入了一组已验证可用的右手开合角参数。

## 9. 第三方组件角色

### 9.1 `pyAgxArm`

- 机械臂 Python SDK
- 直接用于 NERO 控制
- 当前项目优先使用仓库内本地副本

### 9.2 `Omnihand-2025-SDK`

- 智元灵巧手厂商 SDK
- 当前项目已经在其基础上完成 Python 侧集成和串口适配

### 9.3 `agx_arm_ros`

- 机械臂 ROS2 仓库
- 当前项目主流程暂未依赖它
- 更适合后续接 MoveIt、ROS2 节点化或更大系统集成

## 10. 已知限制与当前状态

### 10.1 已跑通的部分

- OmniHand 串口连接
- OmniHand 开合动作
- 机械臂 hover 跟随目标
- 基于模板的抓取位姿脚本雏形

### 10.2 当前问题

- RealSense 在 WSL 环境下存在“能枚举设备但无法稳定启动取流”的情况
- `pick_lying_bottle_template.py` 依赖相机取流，因此在该问题未解决前无法完整验证
- `move_p` 对目标位姿可达性较敏感，需要配合可达性探测与分步扫描脚本

### 10.3 工程建议

- 先把“机械臂到位 + 灵巧手开闭”作为稳定接口固化
- 再单独解决 RealSense 取流问题
- 最后再做完整闭环抓取

## 11. 推荐阅读顺序

如果新同学要快速接手，建议按下面顺序看：

1. `config/sort_trash_pipeline.example.yaml`
2. `scripts/dev/check_setup.py`
3. `scripts/control/hover_detected_target.py`
4. `scripts/omnihand_actions.py`
5. `scripts/control/run_sort_trash_pipeline.py`
6. `scripts/control/pick_lying_bottle_template.py`
7. `scripts/calibration/` 目录

## 12. 一句话总结

这个项目本质上是一个“视觉检测 + 坐标变换 + 机械臂位姿控制 + 灵巧手抓取执行”的集成抓取工程；当前最稳定、最适合协作对接的能力，是把 OmniHand 开合封装成简单接口，并由机械臂控制逻辑在到位时触发。
