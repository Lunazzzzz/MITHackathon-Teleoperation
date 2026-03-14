# sort_trash 带教操作文档

这份文档是给老师、助教或带教同学用的。  
目标不是讲很深的原理，而是帮助高中生通过一步一步动手，理解一个机器人系统是如何从“看见”到“动作”的。

---

## 1. 教学方法建议：从“看”到“动”

对于高一学生，不建议一开始就讲底层代码或复杂数学。  
更适合按照项目 README 推荐的“10 步渐进式联调”来带。

### 第 1-4 步：视觉感官阶段

这一阶段重点是让学生先建立“计算机视觉”的直观印象。

建议目标：

- 先看到 D435 的彩色图和深度图
- 再看到 YOLO 识别出的 2D 检测框
- 再看到物体的 3D 坐标

这时学生会明白：

- 相机不仅能“看见”
- 还可以“估计位置”

---

### 第 5-6 步：建立联系阶段

这一阶段最重要。

核心任务：

- 打印 ChArUco 标定板
- 带学生完成手眼标定
- 让他理解“相机坐标”为什么不能直接给机械臂使用

建议解释方式：

> 相机看到的是“相机自己的世界”，机械臂运动的是“机械臂自己的世界”。  
> 标定就是在做这两个世界之间的“翻译”。

---

### 第 7-10 步：逻辑闭环阶段

这一阶段重点不是抓得多准，而是让学生看到一个完整自动化流程：

- 发现目标
- 生成目标上方位姿
- 机械臂移动
- 进入假抓取流程
- 回到回收盒位置

这一步是把“人工智能识别”和“机器人动作”真正连起来。

---

## 2. 项目简明大纲（给学生讲解时可直接使用）

### 2.1 项目核心目标

让机器人实现一个最基本的自动化闭环：

- 看见物体
- 理解物体
- 定位物体
- 执行动作

---

### 2.2 系统四模块架构

#### 视觉模块 `scripts/vision/`

相当于机器人的“眼睛”和一部分“大脑”。

作用：

- 读取相机画面
- 用 YOLO 识别目标
- 估计目标三维坐标

核心脚本：

- `detect_realsense_yolo_xyz.py`

---

#### 标定模块 `scripts/calibration/`

相当于“翻译器”。

作用：

- 建立相机坐标和机械臂坐标之间的关系

核心脚本：

- `solve_eye_to_hand.py`

---

#### 机械臂控制模块 `scripts/control/`

作用：

- 让机械臂执行动作
- 检查安全规则
- 记录关键位姿

核心脚本：

- `_safety.py`

其中最重要的安全规则之一是：

- 末端高度不得低于 `0.10m`

---

#### 流程总控模块 `scripts/control/run_fake_grasp_cycle.py`

作用：

- 把前面的识别、定位、移动串成一套完整流程

流程大意：

- 识别目标
- 去目标上方
- 假抓取
- 去回收盒
- 假释放
- 回到起点

---

### 2.3 硬件系统清单

#### 执行端

- **NERO 机械臂**

负责移动和执行路径。

#### 感知端

- **Intel RealSense D435 深度相机**

既能拍彩色图像，也能测量深度。

#### 计算端

- **Ubuntu 电脑**

负责运行 AI 模型、相机程序和机械臂控制程序。

#### 辅助端

- **ChArUco 标定板**

用于建立相机与机械臂之间的坐标关系。

---

### 2.4 关键技术栈

#### 编程语言

- `Python`

整个项目的主要“胶水语言”。

#### 人工智能

- `YOLO (Ultralytics)`

负责识别瓶子、杯子等目标。

#### 计算机视觉

- `OpenCV`

负责图像处理、角点检测、标定与显示。

#### 驱动接口

- `pyrealsense2`
  - 控制深度相机
- `pyAgxArm`
  - 控制机械臂

#### 数据管理

- `YAML`

用于保存配置文件、位姿记录和回收点。

---

## 3. 10 步渐进式联调（每一步都带终端命令）

下面所有命令默认在 Ubuntu 终端中执行。

---

### 第 1 步：无硬件自测

目的：

- 先确认环境、模型、配置能正常工作

运行命令：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/control/run_sort_trash_pipeline.py \
  --config config/sort_trash_pipeline.example.yaml \
  --allow-cpu \
  --self-test
```

讲解重点：

- 这一步完全不需要相机和机械臂
- 是“系统能不能启动”的最小验证

---

### 第 2 步：只测 RealSense 取流

目的：

- 先让学生看到彩色图和深度图

运行命令：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/vision/view_realsense_stream.py
```

讲解重点：

- 左边通常是彩色图
- 右边通常是深度图
- 深度图能反映“离相机远近”

---

### 第 3 步：RealSense + YOLO 2D 检测

目的：

- 让学生看到 AI 是如何给物体画框的

运行命令：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/vision/detect_realsense_yolo_2d.py --allow-cpu
```

讲解重点：

- 这一步只有“识别是什么、在图上哪里”
- 还没有机械臂坐标

---

### 第 4 步：RealSense + YOLO + 深度，输出 3D 坐标

目的：

- 让学生看到 2D 识别如何变成 3D 坐标

运行命令：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/vision/detect_realsense_yolo_xyz.py --allow-cpu
```

如果已经完成标定，也可以直接显示机械臂基坐标：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/vision/detect_realsense_yolo_xyz.py \
  --allow-cpu \
  --calibration-file ./data/calib_run_02/calibration_result.yaml
```

讲解重点：

- `camera_xyz`：相机坐标系里的位置
- `base_xyz`：机械臂基坐标系里的位置

---

### 第 5 步：做手眼标定

目的：

- 带学生理解“相机坐标”和“机械臂坐标”之间的翻译关系

先准备：

- 打印标准 ChArUco 板

文件位置：

```text
assets/calibration_boards/charuco_11x8_15mm_11mm_dict4x4_50_a4.pdf
```

采集命令：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/calibration/capture_eye_to_hand.py \
  --channel can0 \
  --board-type charuco \
  --board-cols 11 \
  --board-rows 8 \
  --square-size-mm 15 \
  --marker-size-mm 11 \
  --aruco-dict DICT_4X4_50 \
  --samples 15 \
  --output-dir ./data/calib_run_02
```

求解命令：

```bash
python scripts/calibration/solve_eye_to_hand.py \
  --dataset-dir ./data/calib_run_02
```

验证命令：

```bash
python scripts/calibration/verify_eye_to_hand.py \
  --calibration-file ./data/calib_run_02/calibration_result.yaml \
  --channel can0 \
  --camera-serial 241222074755 \
  --samples 5
```

讲解重点：

- 这是整个工程里最核心的一步之一
- 它解决的是“看见的位置如何变成机械臂能用的位置”

---

### 第 6 步：单独测试机械臂

目的：

- 先确认电脑能和机械臂正常通信
- 再测试机械臂是否能执行简单位姿

如果 CAN 没起来，先激活：

```bash
cd /home/robot/project/sort_trash/pyAgxArm/pyAgxArm/scripts/ubuntu
sudo bash can_activate.sh can0 1000000
```

检查命令：

```bash
ip -details link show can0
candump can0
```

机械臂 dry-run 命令：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/control/move_flange_pose.py \
  --channel can0 \
  --pose -450 0 360 40 45 45 \
  --mm \
  --degrees \
  --send-order mode_target_mode \
  --mode-resend 3
```

如果确认没问题，再加 `--go` 真正执行：

```bash
python scripts/control/move_flange_pose.py \
  --channel can0 \
  --pose -450 0 360 40 45 45 \
  --mm \
  --degrees \
  --send-order mode_target_mode \
  --mode-resend 3 \
  --go
```

讲解重点：

- 不是所有笛卡尔位姿都一定可达
- 机器人运动也需要安全与验证

---

### 第 7 步：视觉悬停验证

目的：

- 让学生看到“识别结果 -> 机械臂移动到物体上方”的过程

预览命令：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority \
python scripts/control/hover_detected_target.py \
  --camera-serial 241222074755 \
  --allow-cpu \
  --calibration-file ./data/calib_run_02/calibration_result.yaml
```

真机示例命令：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority \
python scripts/control/hover_detected_target.py \
  --camera-serial 241222074755 \
  --allow-cpu \
  --calibration-file ./data/calib_run_02/calibration_result.yaml \
  --follow-rate-hz 10 \
  --hover-height-m 0.20 \
  --go
```

按键说明：

- `g`：发送一次悬停命令
- `f`：连续跟随
- `q`：退出

讲解重点：

- 识别结果已经开始真正驱动机械臂

---

### 第 8 步：记录流程位姿和回收点

目的：

- 让学生理解“流程中的固定点”和“回收盒位置”也是可以记录的

记录流程位姿：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/control/record_task_poses.py --init-defaults
python scripts/control/record_task_poses.py --record home
python scripts/control/record_task_poses.py --record work
python scripts/control/record_task_poses.py --record standby
```

记录回收盒中心：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/control/record_drop_poses.py --record bottle
python scripts/control/record_drop_poses.py --record cup
```

讲解重点：

- 机器人不仅要找目标
- 还要知道“做完之后去哪里”

---

### 第 9 步：运行完整假抓取流程

目的：

- 跑通“识别 -> 悬停 -> 假抓取 -> 回收 -> 假释放 -> 回家”的完整闭环

运行命令：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority \
python scripts/control/run_fake_grasp_cycle.py \
  --camera-serial 241222074755 \
  --allow-cpu \
  --calibration-file ./data/calib_run_02/calibration_result.yaml \
  --hover-height-m 0.20 \
  --drop-z-m 0.15 \
  --drop-hover-z-m 0.25 \
  --pose-rpy-deg 90 -90 0 \
  --go
```

讲解重点：

- 这是目前最像“完整机器人系统”的一条流程
- 虽然不一定真的抓住物体，但逻辑闭环已经形成

---

### 第 10 步：总控骨架

目的：

- 让学生知道项目后面还可以继续扩展成更完整系统

dry-run 命令：

```bash
cd /home/robot/project/sort_trash
conda activate grasp-gpu
python scripts/control/run_sort_trash_pipeline.py \
  --config config/sort_trash_pipeline.example.yaml \
  --allow-cpu
```

讲解重点：

- 这一步更偏“系统整合”
- 说明整个项目可以继续升级成更完整的自动化流程

---

## 4. 给老师或助教的带教建议

### 4.1 不要一开始讲太多数学

对高中生来说，更重要的是先理解：

- 系统为什么要分模块
- 相机为什么需要深度信息
- 机械臂为什么需要标定

---

### 4.2 先让学生“看到效果”

优先做这些：

- 看彩色图和深度图
- 看 YOLO 检测框
- 看机械臂跟随目标

学生先有兴趣，后面再讲原理更容易理解。

---

### 4.3 把标定讲成“翻译器”

“坐标系转换”对高中生太抽象。  
更容易理解的说法是：

> 相机和机械臂像两个人在说不同语言，标定就是给他们做翻译。

---

### 4.4 把 Fake Grasp 讲成“先排练，再正式上场”

学生通常会问：

> 为什么不直接抓？

可以这样回答：

> 因为真实抓取更复杂，所以工程上常常先做一套“排练版流程”，把路线和逻辑跑通，再加真实抓取装置。

---

## 5. 一句话总结给学生

这个项目展示的是：

> 机器人如何从“看见世界”开始，经过人工智能识别、空间定位和机械臂控制，最后完成一套自动化动作流程。

它不仅是一个程序项目，更是一个把 **人工智能、机器人和工程实践** 结合起来的真实案例。
