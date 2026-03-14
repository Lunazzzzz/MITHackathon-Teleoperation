# TCP偏移设置

本文档详细说明 `tcp_offset` 参数的定义、单位及通过RViz查看法兰盘中心坐标系的操作步骤，帮助您精准配置工具中心点偏移。

## 一、tcp_offset 参数定义

`tcp_offset` 的6个数值依次对应：`[x, y, z, rx, ry, rz]`，各维度含义与单位如下：
| 维度 | 单位 | 说明 |
|------|------|------|
| x/y/z | 米 (m) | 工具中心相对法兰盘中心的**空间位置偏移** |
| rx/ry/rz | 弧度 (rad) | 工具中心相对法兰盘中心的**姿态偏移** |

## 二、查看法兰盘中心坐标系（RViz可视化）

通过以下步骤可在RViz中直观查看机械臂法兰盘中心的坐标系，为TCP偏移配置提供参考。

### 2.1 Piper 机械臂

1. 打开终端窗口，执行以下命令启动RViz可视化：

    ```bash
    cd ~/catkin_ws
    source install/setup.bash
    ros2 launch piper_description display_urdf.launch.py
    ```

2. 在 RViz 界面中操作：

    - 步骤 1：选择正确的坐标系（参考截图）

        ![piper_rviz_tcp_2](../../asserts/pictures/piper_rviz_tcp_2.png)

    - 步骤 2：展开左侧面板的`RobotModel`，打开`Links`选项

        ![piper_rviz_tcp_3](../../asserts/pictures/piper_rviz_tcp_3.png)

    - 步骤 3：在`Links`中勾选需要查看的 link 以显示其坐标系，同时关闭其他无需显示的 link

        ![piper_rviz_tcp_4](../../asserts/pictures/piper_rviz_tcp_4.png)

### 2.2 Nero 机械臂

1. 打开终端窗口，执行以下命令启动 RViz 可视化：

    ```bash
    cd ~/catkin_ws
    source install/setup.bash
    ros2 launch nero_description display_urdf.launch.py
    ```

2. 在 RViz 界面中操作：

    - 步骤 1：选择正确的坐标系（参考截图）

        ![nero_rviz_tcp_1](../../asserts/pictures/nero_rviz_tcp_1.png)

    - 步骤 2：展开左侧面板的`RobotModel`，打开`Links`选项

        ![nero_rviz_tcp_2](../../asserts/pictures/nero_rviz_tcp_2.png)

    - 步骤 3：在`Links`中勾选需要查看的 link 以显示其坐标系，同时关闭其他无需显示的 link

        ![nero_rviz_tcp_3](../../asserts/pictures/nero_rviz_tcp_3.png)